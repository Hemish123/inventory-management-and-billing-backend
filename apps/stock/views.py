from apps.core.mixins import TenantMixin
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone

from utils.response import api_response, api_error
from apps.products.models import BranchStock, Product
from apps.core.models import Branch
from .models import StockMovement, StockTransfer, StockTransferItem
from .serializers import (
    StockMovementSerializer, StockTransferSerializer,
    StockTransferCreateSerializer,
)


class StockMovementViewSet(TenantMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = StockMovement.objects.all()
    serializer_class = StockMovementSerializer
    search_fields = ['product__name', 'reference_id']
    ordering_fields = ['created_at']
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head']

    def get_queryset(self):
        qs = super().get_queryset().select_related('product', 'branch', 'created_by')
        branch_id = self.request.query_params.get('branch')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)
        reason = self.request.query_params.get('reason')
        if reason:
            qs = qs.filter(reason=reason)
            
        if self.request.user.role_name in ['EMPLOYEE', 'USER']:
            qs = qs.filter(created_by=self.request.user)
            
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def update(self, request, *args, **kwargs):
        movement = self.get_object()
        data = request.data
        quantity = int(data.get('quantity', movement.quantity))
        
        with transaction.atomic():
            if quantity != movement.quantity:
                diff = quantity - movement.quantity
                branch_stock, _ = BranchStock.objects.get_or_create(
                    company=movement.company, product=movement.product, branch=movement.branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                branch_stock.quantity += diff
                branch_stock.save()
                
                movement.quantity = quantity
                movement.balance_after = branch_stock.quantity
                movement.save()
                
            serializer = self.get_serializer(movement, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return api_response(data=serializer.data, message='Stock movement updated')
            return api_error(errors=serializer.errors)

    def destroy(self, request, *args, **kwargs):
        movement = self.get_object()
        with transaction.atomic():
            branch_stock, _ = BranchStock.objects.get_or_create(
                company=movement.company, product=movement.product, branch=movement.branch, warehouse=None,
                defaults={'quantity': 0}
            )
            branch_stock.quantity -= movement.quantity
            branch_stock.save()
            movement.delete()
        return api_response(message='Stock movement deleted and stock reverted')

    @action(detail=False, methods=['post'], url_path='adjust')
    def manual_adjustment(self, request):
        """Manual stock adjustment with audit trail."""
        product_id = request.data.get('product')
        branch_id = request.data.get('branch')
        quantity = int(request.data.get('quantity', 0))
        reason = request.data.get('reason', 'MANUAL')
        notes = request.data.get('notes', '')

        if not product_id or not branch_id or quantity == 0:
            return api_error(message='product, branch, and non-zero quantity are required')

        with transaction.atomic():
            branch_stock, _ = BranchStock.objects.get_or_create(
                company=request.user.company, product_id=product_id, branch_id=branch_id, warehouse=None,
                defaults={'quantity': 0}
            )
            branch_stock.quantity += quantity
            branch_stock.save()

            movement = StockMovement.objects.create(
                company=request.user.company,
                product_id=product_id,
                branch_id=branch_id,
                movement_type='IN' if quantity > 0 else 'OUT',
                reason=reason,
                quantity=quantity,
                balance_after=branch_stock.quantity,
                reference_type='manual',
                notes=notes,
                created_by=request.user,
            )

        serializer = self.get_serializer(movement)
        return api_response(data=serializer.data, message='Stock adjusted')


class StockTransferViewSet(TenantMixin, viewsets.ModelViewSet):
    """
    Full stock transfer workflow:
    DRAFT → REQUESTED → APPROVED → IN_TRANSIT → COMPLETED
                      → REJECTED
    """
    permission_classes = [IsAuthenticated]
    queryset = StockTransfer.objects.all()
    serializer_class = StockTransferSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head']

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            'from_branch', 'to_branch', 'created_by', 'approved_by'
        ).prefetch_related('items__product')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
            
        if self.request.user.role_name in ['EMPLOYEE', 'USER']:
            qs = qs.filter(created_by=self.request.user)
            
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create a new stock transfer with items, supporting any initial status."""
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        from_branch_id = data.get('from_branch')
        to_branch_id = data.get('to_branch')
        notes = data.get('notes', '')
        target_status = data.get('status', 'REQUESTED')
        items_data = data.get('items', [])

        try:
            from_branch_id = int(from_branch_id)
            to_branch_id = int(to_branch_id)
        except (ValueError, TypeError):
            return api_error(message='from_branch and to_branch are required and must be valid branch IDs')

        if from_branch_id == to_branch_id:
            return api_error(message='Source and destination branches must be different')

        try:
            from_branch = Branch.objects.get(id=from_branch_id, company=request.user.company)
            to_branch = Branch.objects.get(id=to_branch_id, company=request.user.company)
        except Branch.DoesNotExist:
            return api_error(message='Selected branch does not exist')

        if not isinstance(items_data, list) or len(items_data) == 0:
            return api_error(message='At least one product item is required')

        # Validate items
        validated_items = []
        for it in items_data:
            prod_id = it.get('product')
            if isinstance(prod_id, dict):
                prod_id = prod_id.get('id')
            try:
                product = Product.objects.get(id=prod_id, company=request.user.company)
            except Product.DoesNotExist:
                return api_error(message=f'Product ID {prod_id} not found')

            try:
                qty = int(it.get('quantity', 1))
            except (ValueError, TypeError):
                qty = 1
            if qty <= 0:
                return api_error(message='Quantity must be greater than 0')

            validated_items.append({'product': product, 'quantity': qty})

        # Validate stock availability if status is COMPLETED
        if target_status == 'COMPLETED':
            for it in validated_items:
                product = it['product']
                qty = it['quantity']
                src_stock = BranchStock.objects.filter(
                    company=request.user.company, product=product, branch=from_branch, warehouse=None
                ).first()
                available_qty = src_stock.quantity if src_stock else 0
                if available_qty < qty:
                    return api_error(
                        message=f"Insufficient stock for '{product.name}' in {from_branch.name}. Available: {available_qty}, Requested: {qty}"
                    )

        transfer = StockTransfer.objects.create(
            company=request.user.company,
            from_branch=from_branch,
            to_branch=to_branch,
            notes=notes,
            status=target_status,
            created_by=request.user,
            received_at=timezone.now() if target_status == 'COMPLETED' else None
        )

        if target_status == 'APPROVED':
            transfer.approved_by = request.user
            transfer.approved_at = timezone.now()
            transfer.save()

        for it in validated_items:
            product = it['product']
            qty = it['quantity']
            StockTransferItem.objects.create(
                company=request.user.company,
                transfer=transfer,
                product=product,
                quantity=qty,
                received_quantity=qty if target_status == 'COMPLETED' else 0
            )

            if target_status == 'COMPLETED':
                src_stock, _ = BranchStock.objects.get_or_create(
                    company=request.user.company, product=product, branch=from_branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                src_stock.quantity -= qty
                src_stock.save()

                StockMovement.objects.create(
                    company=request.user.company, product=product, branch=from_branch,
                    movement_type='TRANSFER_OUT', reason='TRANSFER',
                    quantity=-qty, balance_after=src_stock.quantity,
                    reference_type='transfer', reference_id=transfer.transfer_number,
                    notes=f'Stock transfer to {to_branch.name}',
                    created_by=request.user,
                )

                dst_stock, _ = BranchStock.objects.get_or_create(
                    company=request.user.company, product=product, branch=to_branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                dst_stock.quantity += qty
                dst_stock.save()

                StockMovement.objects.create(
                    company=request.user.company, product=product, branch=to_branch,
                    movement_type='TRANSFER_IN', reason='TRANSFER',
                    quantity=qty, balance_after=dst_stock.quantity,
                    reference_type='transfer', reference_id=transfer.transfer_number,
                    notes=f'Stock transfer from {from_branch.name}',
                    created_by=request.user,
                )

        transfer.refresh_from_db()
        return api_response(data=StockTransferSerializer(transfer).data,
                            message=f'Transfer {transfer.transfer_number} created',
                            status_code=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='create-transfer')
    def create_transfer(self, request):
        return self.create(request)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """Update a stock transfer with all fields editable and stock automatic adjustment."""
        transfer = self.get_object()
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)

        from_branch_id = data.get('from_branch', transfer.from_branch_id)
        to_branch_id = data.get('to_branch', transfer.to_branch_id)
        new_status = data.get('status', transfer.status)
        notes = data.get('notes', transfer.notes)
        items_data = data.get('items', None)

        try:
            from_branch_id = int(from_branch_id)
            to_branch_id = int(to_branch_id)
        except (ValueError, TypeError):
            return api_error(message='Invalid branch selection')

        if from_branch_id == to_branch_id:
            return api_error(message='Source and destination branches must be different')

        try:
            new_from_branch = Branch.objects.get(id=from_branch_id, company=request.user.company)
            new_to_branch = Branch.objects.get(id=to_branch_id, company=request.user.company)
        except Branch.DoesNotExist:
            return api_error(message='Selected branch does not exist')

        was_completed = (transfer.status == 'COMPLETED')

        # 1. If previously COMPLETED, revert the old stock changes first
        if was_completed:
            for old_item in transfer.items.all():
                qty = old_item.quantity
                src_stock, _ = BranchStock.objects.get_or_create(
                    company=transfer.company, product=old_item.product, branch=transfer.from_branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                src_stock.quantity += qty
                src_stock.save()

                dst_stock, _ = BranchStock.objects.get_or_create(
                    company=transfer.company, product=old_item.product, branch=transfer.to_branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                dst_stock.quantity -= qty
                dst_stock.save()

                StockMovement.objects.create(
                    company=transfer.company, product=old_item.product, branch=transfer.from_branch,
                    movement_type='IN', reason='STOCK_COUNT',
                    quantity=qty, balance_after=src_stock.quantity,
                    reference_type='transfer_edit', reference_id=transfer.transfer_number,
                    notes=f'Stock reverted before updating transfer {transfer.transfer_number}',
                    created_by=request.user,
                )
                StockMovement.objects.create(
                    company=transfer.company, product=old_item.product, branch=transfer.to_branch,
                    movement_type='OUT', reason='STOCK_COUNT',
                    quantity=-qty, balance_after=dst_stock.quantity,
                    reference_type='transfer_edit', reference_id=transfer.transfer_number,
                    notes=f'Stock reverted before updating transfer {transfer.transfer_number}',
                    created_by=request.user,
                )

        # 2. Update transfer items if provided
        if items_data is not None:
            if not isinstance(items_data, list) or len(items_data) == 0:
                return api_error(message='At least one product item is required')
            
            transfer.items.all().delete()
            for it in items_data:
                prod_id = it.get('product')
                if isinstance(prod_id, dict):
                    prod_id = prod_id.get('id')
                try:
                    product = Product.objects.get(id=prod_id, company=request.user.company)
                except Product.DoesNotExist:
                    return api_error(message=f'Product ID {prod_id} not found')
                
                try:
                    qty = int(it.get('quantity', 1))
                except (ValueError, TypeError):
                    qty = 1
                if qty <= 0:
                    return api_error(message='Quantity must be greater than 0')

                StockTransferItem.objects.create(
                    company=transfer.company,
                    transfer=transfer,
                    product=product,
                    quantity=qty,
                    received_quantity=qty if new_status == 'COMPLETED' else 0
                )

        # 3. Update transfer header fields
        transfer.from_branch = new_from_branch
        transfer.to_branch = new_to_branch
        transfer.status = new_status
        transfer.notes = notes
        if new_status == 'COMPLETED' and not transfer.received_at:
            transfer.received_at = timezone.now()
        elif new_status == 'APPROVED' and not transfer.approved_at:
            transfer.approved_by = request.user
            transfer.approved_at = timezone.now()
        transfer.save()

        # 4. If newly COMPLETED, apply stock deductions from new_from_branch and additions to new_to_branch
        if new_status == 'COMPLETED':
            for item in transfer.items.all():
                qty = item.quantity
                src_stock = BranchStock.objects.filter(
                    company=transfer.company, product=item.product, branch=new_from_branch, warehouse=None
                ).first()
                available_qty = src_stock.quantity if src_stock else 0
                if available_qty < qty:
                    return api_error(
                        message=f"Insufficient stock for '{item.product.name}' in {new_from_branch.name}. Available: {available_qty}, Requested: {qty}"
                    )

            for item in transfer.items.all():
                qty = item.quantity
                src_stock, _ = BranchStock.objects.get_or_create(
                    company=transfer.company, product=item.product, branch=new_from_branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                src_stock.quantity -= qty
                src_stock.save()

                StockMovement.objects.create(
                    company=transfer.company, product=item.product, branch=new_from_branch,
                    movement_type='TRANSFER_OUT', reason='TRANSFER',
                    quantity=-qty, balance_after=src_stock.quantity,
                    reference_type='transfer', reference_id=transfer.transfer_number,
                    notes=f'Stock transfer to {new_to_branch.name}',
                    created_by=request.user,
                )

                dst_stock, _ = BranchStock.objects.get_or_create(
                    company=transfer.company, product=item.product, branch=new_to_branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                dst_stock.quantity += qty
                dst_stock.save()

                StockMovement.objects.create(
                    company=transfer.company, product=item.product, branch=new_to_branch,
                    movement_type='TRANSFER_IN', reason='TRANSFER',
                    quantity=qty, balance_after=dst_stock.quantity,
                    reference_type='transfer', reference_id=transfer.transfer_number,
                    notes=f'Stock transfer from {new_from_branch.name}',
                    created_by=request.user,
                )
                item.received_quantity = qty
                item.save()

        transfer.refresh_from_db()
        return api_response(data=StockTransferSerializer(transfer).data, message=f'Transfer {transfer.transfer_number} updated')

    @action(detail=True, methods=['post'], url_path='approve')
    def approve_transfer(self, request, pk=None):
        """Approve a requested transfer."""
        transfer = self.get_object()
        if transfer.status != 'REQUESTED':
            return api_error(message='Only requested transfers can be approved')

        transfer.status = 'APPROVED'
        transfer.approved_by = request.user
        transfer.approved_at = timezone.now()
        transfer.save()

        return api_response(message=f'Transfer {transfer.transfer_number} approved')

    @action(detail=True, methods=['post'], url_path='reject')
    def reject_transfer(self, request, pk=None):
        """Reject a requested transfer."""
        transfer = self.get_object()
        if transfer.status != 'REQUESTED':
            return api_error(message='Only requested transfers can be rejected')

        transfer.status = 'REJECTED'
        transfer.rejected_reason = request.data.get('reason', '')
        transfer.approved_by = request.user
        transfer.approved_at = timezone.now()
        transfer.save()

        return api_response(message=f'Transfer {transfer.transfer_number} rejected')

    @action(detail=True, methods=['post'], url_path='complete')
    def complete_transfer(self, request, pk=None):
        """
        Complete an approved transfer:
        - Deducts stock from source branch
        - Adds stock to destination branch
        - Creates audit trail movements
        """
        transfer = self.get_object()
        if transfer.status not in ('APPROVED', 'IN_TRANSIT'):
            return api_error(message='Only approved or in-transit transfers can be completed')

        from apps.products.models import BranchStock

        with transaction.atomic():
            # Validate stock availability first
            for item in transfer.items.all():
                qty = item.quantity
                src_stock = BranchStock.objects.filter(
                    company=transfer.company, product=item.product, branch=transfer.from_branch, warehouse=None
                ).first()
                
                available_qty = src_stock.quantity if src_stock else 0
                if available_qty < qty:
                    return api_error(message=f"Cannot complete transfer. Insufficient stock for '{item.product.name}'. Available: {available_qty}, Requested: {qty}")

            for item in transfer.items.all():
                qty = item.quantity

                # Deduct from source
                src_stock = BranchStock.objects.get(
                    company=transfer.company, product=item.product, branch=transfer.from_branch, warehouse=None
                )
                src_stock.quantity -= qty
                src_stock.save()

                StockMovement.objects.create(
                    company=transfer.company, product=item.product, branch=transfer.from_branch,
                    movement_type='TRANSFER_OUT', reason='TRANSFER',
                    quantity=-qty, balance_after=src_stock.quantity,
                    reference_type='transfer', reference_id=transfer.transfer_number,
                    created_by=request.user,
                )

                # Add to destination
                dst_stock, _ = BranchStock.objects.get_or_create(
                    company=transfer.company, product=item.product, branch=transfer.to_branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                dst_stock.quantity += qty
                dst_stock.save()

                StockMovement.objects.create(
                    company=transfer.company, product=item.product, branch=transfer.to_branch,
                    movement_type='TRANSFER_IN', reason='TRANSFER',
                    quantity=qty, balance_after=dst_stock.quantity,
                    reference_type='transfer', reference_id=transfer.transfer_number,
                    created_by=request.user,
                )

                item.received_quantity = qty
                item.save()

            transfer.status = 'COMPLETED'
            transfer.received_at = timezone.now()
            transfer.save()

        return api_response(message=f'Transfer {transfer.transfer_number} completed — stock updated')

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_transfer(self, request, pk=None):
        """Cancel a transfer (only if not yet completed)."""
        transfer = self.get_object()
        if transfer.status == 'COMPLETED':
            return api_error(message='Completed transfers cannot be cancelled')

        transfer.status = 'CANCELLED'
        transfer.save()
        return api_response(message=f'Transfer {transfer.transfer_number} cancelled')

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """Delete a stock transfer and adjust stock if transfer was completed."""
        transfer = self.get_object()

        # If the transfer was completed, revert stock back to source branch
        if transfer.status == 'COMPLETED':
            for item in transfer.items.all():
                qty = item.quantity
                src_stock, _ = BranchStock.objects.get_or_create(
                    company=transfer.company, product=item.product, branch=transfer.from_branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                src_stock.quantity += qty
                src_stock.save()

                dst_stock, _ = BranchStock.objects.get_or_create(
                    company=transfer.company, product=item.product, branch=transfer.to_branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                dst_stock.quantity -= qty
                dst_stock.save()

                StockMovement.objects.create(
                    company=transfer.company, product=item.product, branch=transfer.from_branch,
                    movement_type='IN', reason='STOCK_COUNT',
                    quantity=qty, balance_after=src_stock.quantity,
                    reference_type='transfer_revert', reference_id=transfer.transfer_number,
                    notes=f'Stock reverted due to deleted transfer {transfer.transfer_number}',
                    created_by=request.user,
                )
                StockMovement.objects.create(
                    company=transfer.company, product=item.product, branch=transfer.to_branch,
                    movement_type='OUT', reason='STOCK_COUNT',
                    quantity=-qty, balance_after=dst_stock.quantity,
                    reference_type='transfer_revert', reference_id=transfer.transfer_number,
                    notes=f'Stock reverted due to deleted transfer {transfer.transfer_number}',
                    created_by=request.user,
                )

        transfer_number = transfer.transfer_number
        transfer.delete()
        return api_response(message=f'Transfer {transfer_number} deleted and stock adjusted successfully')
