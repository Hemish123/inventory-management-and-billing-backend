from apps.core.mixins import TenantMixin
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone

from utils.response import api_response, api_error
from apps.products.models import BranchStock
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

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            'from_branch', 'to_branch', 'created_by', 'approved_by'
        ).prefetch_related('items__product')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    @action(detail=False, methods=['post'], url_path='create-transfer')
    def create_transfer(self, request):
        """Create a new stock transfer with items."""
        ser = StockTransferCreateSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)

        data = ser.validated_data
        if data['from_branch'] == data['to_branch']:
            return api_error(message='Source and destination branches must be different')

        # Validate stock availability
        from apps.products.models import BranchStock
        for item_data in data['items']:
            product = item_data['product']
            qty = item_data['quantity']
            src_stock = BranchStock.objects.filter(
                company=request.user.company,
                product=product,
                branch_id=data['from_branch'],
                warehouse=None
            ).first()
            
            available_qty = src_stock.quantity if src_stock else 0
            if available_qty < qty:
                return api_error(
                    message=f"Insufficient stock for '{product.name}'. Available: {available_qty}, Requested: {qty}"
                )

        with transaction.atomic():
            transfer = StockTransfer.objects.create(
                company=request.user.company,
                from_branch_id=data['from_branch'],
                to_branch_id=data['to_branch'],
                notes=data.get('notes', ''),
                status='REQUESTED',
                created_by=request.user,
            )
            for item_data in data['items']:
                from .models import StockTransferItem
                StockTransferItem.objects.create(
                    company=request.user.company,
                    transfer=transfer,
                    product=item_data['product'],
                    quantity=item_data['quantity'],
                )

        result = StockTransferSerializer(transfer)
        return api_response(data=result.data, message=f'Transfer {transfer.transfer_number} created',
                            status_code=status.HTTP_201_CREATED)

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
