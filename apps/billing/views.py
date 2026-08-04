from apps.core.mixins import TenantMixin
from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db import transaction

from utils.response import api_response, api_error
from apps.core.models import Branch
from apps.products.models import Product, BranchStock
from apps.stock.models import StockMovement
from .models import Bill, BillItem, BillPayment, BillSequence
from .serializers import (
    BillSerializer, BillCreateSerializer, BillListSerializer,
)


class BillViewSet(TenantMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Bill.objects.all()
    search_fields = ['bill_number', 'customer_name', 'customer_phone']
    ordering_fields = ['billing_date', 'grand_total']

    def get_serializer_class(self):
        if self.action == 'list':
            return BillListSerializer
        return BillSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related('branch', 'cashier', 'customer')
        branch_id = self.request.query_params.get('branch')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
            
        if self.request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(cashier=self.request.user)
            
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    @action(detail=True, methods=['get'], url_path='pdf', permission_classes=[])
    def download_pdf(self, request, pk=None):
        from .pdf_generator import generate_bill_pdf
        from django.http import HttpResponse
        from django.shortcuts import get_object_or_404
        from .models import Bill
        
        # We bypass get_object() because this endpoint is accessed via a new tab
        # without a JWT token (AnonymousUser), so TenantMixin would block it.
        bill = get_object_or_404(Bill, pk=pk)
        
        pdf_bytes = generate_bill_pdf(bill)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Bill_{bill.bill_number.replace("/", "-")}.pdf"'
        return response

    # ──────────────────────────────────────────────────────────────
    # Core bill creation — supports COMPLETED, DRAFT, and HOLD
    # ──────────────────────────────────────────────────────────────
    @action(detail=False, methods=['post'], url_path='create-bill')
    def create_bill(self, request):
        serializer = BillCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)

        data = serializer.validated_data
        items_data = data['items']
        if not items_data:
            return api_error(message='At least one item is required')

        try:
            branch = Branch.objects.get(id=data['branch_id'])
        except Branch.DoesNotExist:
            return api_error(message='Branch not found')

        # Determine target status
        if data.get('save_as_draft'):
            target_status = 'DRAFT'
        elif data.get('save_as_hold'):
            target_status = 'HOLD'
        else:
            target_status = 'COMPLETED'

        try:
            with transaction.atomic():
                bill_number = BillSequence.next_bill_number(branch)

                # Calculate totals from items
                subtotal = sum(item['line_total'] for item in items_data)
                tax_total = sum(item.get('tax_amount', Decimal('0')) for item in items_data)

                # Overall discount
                discount_type = data.get('discount_type', 'NONE')
                discount_pct = data.get('discount_percentage', Decimal('0'))
                discount_amount = data.get('discount_amount', Decimal('0'))
                if discount_type == 'PERCENTAGE' and discount_pct > 0:
                    discount_amount = subtotal * discount_pct / 100

                round_off = data.get('round_off', Decimal('0'))
                grand_total = subtotal + tax_total - discount_amount + round_off
                amount_received = data.get('amount_received', grand_total)
                change_due = max(Decimal('0'), amount_received - grand_total)

                bill = Bill.objects.create(
                    company=request.user.company,
                    bill_number=bill_number,
                    branch=branch,
                    customer_id=data.get('customer_id'),
                    customer_name=data.get('customer_name', 'Walk-in Customer'),
                    customer_phone=data.get('customer_phone', ''),
                    status=target_status,
                    subtotal=subtotal,
                    tax_total=tax_total,
                    discount_type=discount_type,
                    discount_amount=discount_amount,
                    discount_percentage=discount_pct,
                    round_off=round_off,
                    grand_total=grand_total,
                    payment_method=data['payment_method'],
                    amount_received=amount_received,
                    change_due=change_due,
                    notes=data.get('notes', ''),
                    cashier=request.user,
                )

                # Create line items
                for item_data in items_data:
                    product = Product.objects.get(id=item_data['product'])
                    BillItem.objects.create(
                        company=request.user.company,
                        bill=bill,
                        product=product,
                        product_name=item_data.get('product_name', product.name),
                        barcode=item_data.get('barcode', product.barcode),
                        hsn_code=item_data.get('hsn_code', product.hsn_code),
                        quantity=item_data['quantity'],
                        unit_price=item_data['unit_price'],
                        discount_type=item_data.get('discount_type', 'NONE'),
                        discount_percentage=item_data.get('discount_percentage', Decimal('0')),
                        discount_amount=item_data.get('discount_amount', Decimal('0')),
                        tax_percentage=item_data.get('tax_percentage', 0),
                        tax_amount=item_data.get('tax_amount', Decimal('0')),
                        line_total=item_data['line_total'],
                    )

                # Create split payment records
                if data['payment_method'] == 'SPLIT' and data.get('payments'):
                    for pay in data['payments']:
                        BillPayment.objects.create(
                            company=request.user.company,
                            bill=bill,
                            payment_method=pay['payment_method'],
                            amount=pay['amount'],
                            reference=pay.get('reference', ''),
                        )

                # Only deduct stock for COMPLETED bills (not DRAFT/HOLD)
                if target_status == 'COMPLETED':
                    self._deduct_stock(bill, request.user)
        except ValueError as e:
            return api_error(message=str(e))

        result_serializer = BillSerializer(bill)
        msg = {
            'DRAFT': f'Draft {bill_number} saved',
            'HOLD': f'Bill {bill_number} held',
            'COMPLETED': f'Bill {bill_number} created successfully',
        }[target_status]

        return api_response(
            data=result_serializer.data,
            message=msg,
            status_code=status.HTTP_201_CREATED
        )

    # ──────────────────────────────────────────────────────────────
    # Draft / Hold management
    # ──────────────────────────────────────────────────────────────
    @action(detail=False, methods=['get'], url_path='drafts')
    def list_drafts(self, request):
        """List all DRAFT and HOLD bills for the current branch."""
        qs = self.get_queryset().filter(
            status__in=['DRAFT', 'HOLD']
        ).order_by('-billing_date')
        branch_id = request.query_params.get('branch')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        serializer = BillListSerializer(qs, many=True)
        return api_response(data=serializer.data)

    @action(detail=True, methods=['get'], url_path='resume')
    def resume_bill(self, request, pk=None):
        """Load a draft/held bill for editing — returns full bill with items."""
        bill = self.get_object()
        if bill.status not in ('DRAFT', 'HOLD'):
            return api_error(message='Only draft or held bills can be resumed')
        serializer = BillSerializer(bill)
        return api_response(data=serializer.data)

    @action(detail=True, methods=['post'], url_path='finalize')
    def finalize_bill(self, request, pk=None):
        """Convert a DRAFT/HOLD bill to COMPLETED — deducts stock."""
        bill = self.get_object()
        if bill.status not in ('DRAFT', 'HOLD'):
            return api_error(message='Only draft or held bills can be finalized')

        try:
            with transaction.atomic():
                # Update payment info if provided
                payment_method = request.data.get('payment_method', bill.payment_method)
                amount_received = Decimal(str(request.data.get('amount_received', bill.grand_total)))
                change_due = max(Decimal('0'), amount_received - bill.grand_total)

                bill.status = 'COMPLETED'
                bill.payment_method = payment_method
                bill.amount_received = amount_received
                bill.change_due = change_due
                bill.save()

                # Create split payments if provided
                payments_data = request.data.get('payments', [])
                if payment_method == 'SPLIT' and payments_data:
                    bill.payments.all().delete()  # Clear any previous
                    for pay in payments_data:
                        BillPayment.objects.create(
                            company=bill.company,
                            bill=bill,
                            payment_method=pay['payment_method'],
                            amount=Decimal(str(pay['amount'])),
                            reference=pay.get('reference', ''),
                        )

                # NOW deduct stock
                self._deduct_stock(bill, request.user)
        except ValueError as e:
            return api_error(message=str(e))

        result_serializer = BillSerializer(bill)
        return api_response(
            data=result_serializer.data,
            message=f'Bill {bill.bill_number} finalized'
        )

    @action(detail=True, methods=['delete'], url_path='discard')
    def discard_draft(self, request, pk=None):
        """Delete a draft/held bill — no stock impact."""
        bill = self.get_object()
        if bill.status not in ('DRAFT', 'HOLD'):
            return api_error(message='Only draft or held bills can be discarded')
        bill_number = bill.bill_number
        bill.delete()
        return api_response(message=f'Draft {bill_number} discarded')

    # ──────────────────────────────────────────────────────────────
    # Void a completed bill (reverses stock)
    # ──────────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='void')
    def void_bill(self, request, pk=None):
        bill = self.get_object()
        if bill.status == 'VOID':
            return api_error(message='Bill is already voided')
        if bill.status in ('DRAFT', 'HOLD'):
            return api_error(message='Cannot void a draft/held bill — discard it instead')

        with transaction.atomic():
            bill.status = 'VOID'
            bill.save()

            for item in bill.items.all():
                qty = int(item.quantity)
                branch_stock, _ = BranchStock.objects.get_or_create(
                    company=bill.company, product=item.product, branch=bill.branch, warehouse=None,
                    defaults={'quantity': 0}
                )
                branch_stock.quantity += qty
                branch_stock.save()

                StockMovement.objects.create(
                    company=bill.company,
                    product=item.product,
                    branch=bill.branch,
                    movement_type='IN',
                    reason='RETURN',
                    quantity=qty,
                    balance_after=branch_stock.quantity,
                    reference_type='bill_void',
                    reference_id=bill.bill_number,
                    created_by=request.user,
                )

        return api_response(message='Bill voided and stock restored')

    # ──────────────────────────────────────────────────────────────
    # Private helper — stock deduction
    # ──────────────────────────────────────────────────────────────
    def _deduct_stock(self, bill, user):
        """Deduct stock for all items in a bill. Must be called inside transaction.atomic()."""
        # 1. Validation pass
        for item in bill.items.select_related('product'):
            qty = int(item.quantity)
            branch_stock = BranchStock.objects.filter(
                company=bill.company, product=item.product, branch=bill.branch, warehouse=None
            ).first()
            available_qty = branch_stock.quantity if branch_stock else 0
            if available_qty < qty:
                raise ValueError(f"Insufficient stock for '{item.product.name}'. Available: {available_qty}, Requested: {qty}")
                
        # 2. Deduction pass
        for item in bill.items.select_related('product'):
            qty = int(item.quantity)
            branch_stock = BranchStock.objects.get(
                company=bill.company, product=item.product, branch=bill.branch, warehouse=None
            )
            branch_stock.quantity -= qty
            branch_stock.save()

            StockMovement.objects.create(
                company=bill.company,
                product=item.product,
                branch=bill.branch,
                movement_type='OUT',
                reason='SALE',
                quantity=-qty,
                balance_after=branch_stock.quantity,
                reference_type='bill',
                reference_id=bill.bill_number,
                created_by=user,
            )
