from apps.core.mixins import TenantMixin
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db import transaction

from utils.response import api_response, api_error
from apps.products.models import BranchStock
from apps.stock.models import StockMovement
from .models import Purchase, PurchaseItem
from .serializers import PurchaseSerializer, PurchaseListSerializer


class PurchaseViewSet(TenantMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Purchase.objects.all()
    search_fields = ['po_number', 'supplier__name']
    ordering_fields = ['purchase_date', 'total_amount']

    def get_serializer_class(self):
        if self.action == 'list':
            return PurchaseListSerializer
        return PurchaseSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related('supplier', 'branch', 'created_by')
        branch_id = self.request.query_params.get('branch')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        return qs

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        # 1. Generate PO Number if missing
        if not data.get('po_number'):
            from django.utils import timezone
            import random
            random_suffix = ''.join([str(random.randint(0, 9)) for _ in range(4)])
            data['po_number'] = f"PO-{timezone.now().strftime('%Y%m%d')}-{random_suffix}"

        # 2. Map branch_id to branch
        if 'branch_id' in data and 'branch' not in data:
            data['branch'] = data['branch_id']
            
        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            # Bypass TenantMixin perform_create to inject both company and created_by safely
            purchase = serializer.save(
                company=request.user.company,
                created_by=request.user
            )
            
            # 3. Create items
            items_data = request.data.get('items', [])
            if isinstance(items_data, list):
                for item in items_data:
                    PurchaseItem.objects.create(
                        company=request.user.company,
                        purchase=purchase,
                        product_id=item.get('product'),
                        quantity=item.get('quantity', 0),
                        unit_cost=item.get('unit_cost', 0),
                        received_quantity=0,
                    )
            
            return api_response(data=self.get_serializer(purchase).data, message='Purchase order created',
                                status_code=status.HTTP_201_CREATED)
        return api_error(errors=serializer.errors)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    @action(detail=True, methods=['post'], url_path='receive')
    def receive_purchase(self, request, pk=None):
        """Mark a purchase as received and update stock."""
        purchase = self.get_object()
        if purchase.status in ('RECEIVED', 'CANCELLED'):
            return api_error(message='Purchase is already received or cancelled')

        with transaction.atomic():
            for item in purchase.items.select_related('product'):
                qty = item.quantity - item.received_quantity
                if qty <= 0:
                    continue

                branch_stock, _ = BranchStock.objects.get_or_create(
                    company=purchase.company, product=item.product, branch=purchase.branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                branch_stock.quantity += qty
                branch_stock.save()

                StockMovement.objects.create(
                    company=purchase.company,
                    product=item.product,
                    branch=purchase.branch,
                    movement_type='IN',
                    reason='PURCHASE',
                    quantity=qty,
                    balance_after=branch_stock.quantity,
                    reference_type='purchase',
                    reference_id=purchase.po_number,
                    created_by=request.user,
                )

                item.received_quantity = item.quantity
                item.save()

            purchase.status = 'RECEIVED'
            purchase.save()

        return api_response(message='Purchase received — stock updated')

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        purchase = self.get_object()
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        if purchase.status == 'RECEIVED':
            for item in purchase.items.select_related('product'):
                qty = item.received_quantity
                if qty > 0:
                    branch_stock, _ = BranchStock.objects.get_or_create(
                        company=purchase.company, product=item.product, branch=purchase.branch, warehouse=None,
                        defaults={'quantity': 0}
                    )
                    branch_stock.quantity -= qty
                    branch_stock.save()
                    StockMovement.objects.create(
                        company=purchase.company,
                        product=item.product,
                        branch=purchase.branch,
                        movement_type='OUT',
                        reason='ADJUSTMENT',
                        quantity=-qty,
                        balance_after=branch_stock.quantity,
                        reference_type='purchase_update_revert',
                        reference_id=purchase.po_number,
                        created_by=request.user,
                    )
        
        if 'branch_id' in data and 'branch' not in data:
            data['branch'] = data['branch_id']
            
        serializer = self.get_serializer(purchase, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            
            if 'items' in data:
                purchase.items.all().delete()
                for item in data['items']:
                    PurchaseItem.objects.create(
                        company=purchase.company,
                        purchase=purchase,
                        product_id=item.get('product'),
                        quantity=item.get('quantity', 0),
                        unit_cost=item.get('unit_cost', 0),
                        received_quantity=0,
                    )
                
            if purchase.status == 'RECEIVED':
                purchase.status = 'PENDING'
                purchase.save()
                
                # Re-apply receive logic inline to avoid returning early
                for item in purchase.items.select_related('product'):
                    qty = item.quantity
                    if qty <= 0:
                        continue
                    branch_stock, _ = BranchStock.objects.get_or_create(
                        company=purchase.company, product=item.product, branch=purchase.branch, warehouse=None,
                        defaults={'quantity': 0}
                    )
                    branch_stock.quantity += qty
                    branch_stock.save()
                    StockMovement.objects.create(
                        company=purchase.company,
                        product=item.product,
                        branch=purchase.branch,
                        movement_type='IN',
                        reason='PURCHASE',
                        quantity=qty,
                        balance_after=branch_stock.quantity,
                        reference_type='purchase',
                        reference_id=purchase.po_number,
                        created_by=request.user,
                    )
                    item.received_quantity = item.quantity
                    item.save()
                purchase.status = 'RECEIVED'
                purchase.save()
            
            return api_response(data=self.get_serializer(purchase).data, message='Purchase updated')
        return api_error(errors=serializer.errors)

    def destroy(self, request, *args, **kwargs):
        purchase = self.get_object()
        with transaction.atomic():
            if purchase.status == 'RECEIVED':
                for item in purchase.items.select_related('product'):
                    qty = item.received_quantity
                    if qty > 0:
                        branch_stock, _ = BranchStock.objects.get_or_create(
                            company=purchase.company, product=item.product, branch=purchase.branch, warehouse=None,
                            defaults={'quantity': 0}
                        )
                        branch_stock.quantity -= qty
                        branch_stock.save()

                        StockMovement.objects.create(
                            company=purchase.company,
                            product=item.product,
                            branch=purchase.branch,
                            movement_type='OUT',
                            reason='ADJUSTMENT',
                            quantity=-qty,
                            balance_after=branch_stock.quantity,
                            reference_type='purchase_delete',
                            reference_id=purchase.po_number,
                            created_by=request.user,
                        )
            response = super().destroy(request, *args, **kwargs)
        return response
