import csv
import io
from decimal import Decimal
from datetime import timedelta, date

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, F, Q, Avg, Max, Min
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from django.http import HttpResponse

from utils.response import api_response
from apps.billing.models import Bill, BillItem
from apps.products.models import Product, BranchStock
from apps.stock.models import StockMovement
from apps.purchases.models import Purchase, PurchaseItem
from apps.customers.models import Customer
from apps.core.models import Branch


def _parse_dates(request):
    """Helper to parse date range from query params."""
    today = timezone.now().date()
    start = request.query_params.get('start_date')
    end = request.query_params.get('end_date')
    start_date = date.fromisoformat(start) if start else today.replace(day=1)
    end_date = date.fromisoformat(end) if end else today
    return start_date, end_date


def _csv_response(rows, headers, filename):
    """Helper to generate a CSV HttpResponse."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ──────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────
class DashboardStatsView(APIView):
    """Top-level KPIs for the RetailTrack dashboard."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        branch_id = request.query_params.get('branch')
        today = timezone.now().date()
        month_start = today.replace(day=1)

        bills_qs = Bill.objects.filter(company=request.user.company, status='COMPLETED')
        if request.user.role_name == 'EMPLOYEE':
            bills_qs = bills_qs.filter(cashier=request.user)
        if branch_id:
            bills_qs = bills_qs.filter(branch_id=branch_id)

        today_bills = bills_qs.filter(billing_date__date=today)
        month_bills = bills_qs.filter(billing_date__date__gte=month_start)

        today_revenue = today_bills.aggregate(s=Sum('grand_total'))['s'] or 0
        month_revenue = month_bills.aggregate(s=Sum('grand_total'))['s'] or 0
        today_bill_count = today_bills.count()
        month_bill_count = month_bills.count()

        product_count = Product.objects.filter(company=request.user.company, is_active=True).count()

        stock_qs = BranchStock.objects.filter(company=request.user.company).select_related('product')
        if branch_id:
            stock_qs = stock_qs.filter(branch_id=branch_id)

        low_stock_count = sum(
            1 for bs in stock_qs if bs.quantity < bs.product.minimum_stock_level
        )

        pending_purchases_qs = Purchase.objects.filter(company=request.user.company, status__in=['DRAFT', 'ORDERED', 'PARTIAL'])
        if request.user.role_name == 'EMPLOYEE':
            pending_purchases_qs = pending_purchases_qs.filter(created_by=request.user)
        pending_purchases = pending_purchases_qs.count()

        data = {
            'today_revenue': float(today_revenue),
            'month_revenue': float(month_revenue),
            'today_bills': today_bill_count,
            'month_bills': month_bill_count,
            'total_products': product_count,
            'low_stock_alerts': low_stock_count,
            'pending_purchases': pending_purchases,
        }
        return api_response(data=data)


# ──────────────────────────────────────────────────────────
# Sales Report
# ──────────────────────────────────────────────────────────
class SalesReportView(APIView):
    """Sales report with date range and branch filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date, end_date = _parse_dates(request)
        branch_id = request.query_params.get('branch')

        qs = Bill.objects.filter(
            company=request.user.company,
            status='COMPLETED',
            billing_date__date__gte=start_date,
            billing_date__date__lte=end_date,
        )
        if request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(cashier=request.user)
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        daily = qs.annotate(
            day=TruncDate('billing_date')
        ).values('day').annotate(
            total=Sum('grand_total'),
            tax=Sum('tax_total'),
            discount=Sum('discount_amount'),
            count=Count('id')
        ).order_by('day')

        summary = qs.aggregate(
            total_revenue=Sum('grand_total'),
            total_tax=Sum('tax_total'),
            total_discount=Sum('discount_amount'),
            total_bills=Count('id'),
            avg_bill=Avg('grand_total'),
        )

        data = {
            'summary': {k: float(v or 0) for k, v in summary.items()},
            'daily': [{
                'date': d['day'].isoformat(),
                'revenue': float(d['total'] or 0),
                'tax': float(d['tax'] or 0),
                'discount': float(d['discount'] or 0),
                'bills': d['count'],
            } for d in daily],
        }

        # Export support
        if request.query_params.get('export') == 'csv':
            rows = [[d['date'], d['revenue'], d['tax'], d['discount'], d['bills']] for d in data['daily']]
            return _csv_response(rows, ['Date', 'Revenue', 'Tax', 'Discount', 'Bills'], 'sales_report.csv')

        return api_response(data=data)


class SalesTrendView(APIView):
    """Daily sales for the last 30 days."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        branch_id = request.query_params.get('branch')
        thirty_days_ago = timezone.now().date() - timedelta(days=30)

        qs = Bill.objects.filter(company=request.user.company, status='COMPLETED', billing_date__date__gte=thirty_days_ago)
        if request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(cashier=request.user)
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        daily = qs.annotate(day=TruncDate('billing_date')).values('day').annotate(
            total=Sum('grand_total'), count=Count('id')
        ).order_by('day')

        data = [{'date': d['day'].isoformat(), 'revenue': float(d['total'] or 0), 'bills': d['count']} for d in daily]
        return api_response(data=data)


# ──────────────────────────────────────────────────────────
# Purchase Report
# ──────────────────────────────────────────────────────────
class PurchaseReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date, end_date = _parse_dates(request)
        branch_id = request.query_params.get('branch')

        qs = Purchase.objects.filter(company=request.user.company, purchase_date__gte=start_date, purchase_date__lte=end_date)
        if request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(created_by=request.user)
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        summary = qs.aggregate(
            total_amount=Sum('total_amount'),
            total_gst=Sum('gst_amount'),
            total_orders=Count('id'),
        )

        purchases = qs.select_related('supplier', 'branch').values(
            'po_number', 'supplier__name', 'branch__name',
            'purchase_date', 'total_amount', 'gst_amount', 'status'
        ).order_by('-purchase_date')

        data = {
            'summary': {k: float(v or 0) for k, v in summary.items()},
            'purchases': list(purchases),
        }

        if request.query_params.get('export') == 'csv':
            rows = [[p['po_number'], p['supplier__name'], p['branch__name'],
                      str(p['purchase_date']), float(p['total_amount'] or 0), p['status']]
                     for p in purchases]
            return _csv_response(rows, ['PO#', 'Supplier', 'Branch', 'Date', 'Amount', 'Status'], 'purchase_report.csv')

        return api_response(data=data)


# ──────────────────────────────────────────────────────────
# Inventory / Stock Report
# ──────────────────────────────────────────────────────────
class InventoryReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        branch_id = request.query_params.get('branch')
        qs = BranchStock.objects.filter(company=request.user.company).select_related('product', 'branch', 'product__category')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        data = [{
            'product_name': bs.product.name,
            'sku': bs.product.sku,
            'barcode': bs.product.barcode,
            'category': bs.product.category.name if bs.product.category else '',
            'branch': bs.branch.name,
            'quantity': bs.quantity,
            'cost_price': float(bs.product.cost_price),
            'selling_price': float(bs.product.selling_price),
            'stock_value': float(bs.product.cost_price * bs.quantity),
            'minimum_level': bs.product.minimum_stock_level,
            'reorder_level': bs.product.reorder_level,
        } for bs in qs]

        if request.query_params.get('export') == 'csv':
            rows = [[d['product_name'], d['sku'], d['barcode'], d['branch'],
                      d['quantity'], d['cost_price'], d['stock_value']] for d in data]
            return _csv_response(rows, ['Product', 'SKU', 'Barcode', 'Branch', 'Qty', 'Cost', 'Value'], 'inventory_report.csv')

        return api_response(data=data)


# ──────────────────────────────────────────────────────────
# Top Selling Products
# ──────────────────────────────────────────────────────────
class TopProductsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        branch_id = request.query_params.get('branch')
        start_date, end_date = _parse_dates(request)

        qs = BillItem.objects.filter(
            company=request.user.company,
            bill__status='COMPLETED',
            bill__billing_date__date__gte=start_date,
            bill__billing_date__date__lte=end_date,
        )
        if request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(bill__cashier=request.user)
        if branch_id:
            qs = qs.filter(bill__branch_id=branch_id)

        top = qs.values('product__name', 'product__barcode').annotate(
            total_qty=Sum('quantity'), total_revenue=Sum('line_total')
        ).order_by('-total_qty')[:20]

        data = [{'product_name': t['product__name'], 'barcode': t['product__barcode'],
                 'total_quantity': float(t['total_qty'] or 0),
                 'total_revenue': float(t['total_revenue'] or 0)} for t in top]
        return api_response(data=data)


# ──────────────────────────────────────────────────────────
# Low Stock Report
# ──────────────────────────────────────────────────────────
class LowStockView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        branch_id = request.query_params.get('branch')
        qs = BranchStock.objects.filter(company=request.user.company).select_related('product', 'branch')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        low = [{'product_name': bs.product.name, 'barcode': bs.product.barcode,
                'branch': bs.branch.name, 'current_stock': bs.quantity,
                'minimum_level': bs.product.minimum_stock_level,
                'reorder_level': bs.product.reorder_level,
                'deficit': bs.product.minimum_stock_level - bs.quantity}
               for bs in qs if bs.quantity < bs.product.minimum_stock_level]

        low.sort(key=lambda x: x['deficit'], reverse=True)

        if request.query_params.get('export') == 'csv':
            rows = [[d['product_name'], d['barcode'], d['branch'], d['current_stock'],
                      d['minimum_level'], d['deficit']] for d in low]
            return _csv_response(rows, ['Product', 'Barcode', 'Branch', 'Stock', 'Min Level', 'Deficit'], 'low_stock_report.csv')

        return api_response(data=low)


# ──────────────────────────────────────────────────────────
# Dead Stock (products with zero sales in last 90 days)
# ──────────────────────────────────────────────────────────
class DeadStockView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        days = int(request.query_params.get('days', 90))
        cutoff = timezone.now().date() - timedelta(days=days)

        sold_product_ids = BillItem.objects.filter(
            company=request.user.company, bill__status='COMPLETED', bill__billing_date__date__gte=cutoff
        ).values_list('product_id', flat=True).distinct()

        products = Product.objects.filter(company=request.user.company, is_active=True).exclude(
            id__in=sold_product_ids
        ).select_related('category')

        data = [{'product_name': p.name, 'sku': p.sku, 'barcode': p.barcode,
                 'category': p.category.name if p.category else '',
                 'selling_price': float(p.selling_price),
                 'cost_price': float(p.cost_price)} for p in products]

        return api_response(data=data)


# ──────────────────────────────────────────────────────────
# Branch Sales Report
# ──────────────────────────────────────────────────────────
class BranchSalesReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date, end_date = _parse_dates(request)

        qs = Bill.objects.filter(
            company=request.user.company,
            status='COMPLETED',
            billing_date__date__gte=start_date,
            billing_date__date__lte=end_date,
        )
        if request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(cashier=request.user)

        branch_data = qs.values('branch__name', 'branch__code').annotate(
            total_revenue=Sum('grand_total'),
            total_bills=Count('id'),
            avg_bill=Avg('grand_total'),
        ).order_by('-total_revenue')

        data = [{'branch': b['branch__name'], 'code': b['branch__code'],
                 'revenue': float(b['total_revenue'] or 0),
                 'bills': b['total_bills'],
                 'avg_bill': float(b['avg_bill'] or 0)} for b in branch_data]

        return api_response(data=data)


# ──────────────────────────────────────────────────────────
# Supplier Purchase Report
# ──────────────────────────────────────────────────────────
class SupplierPurchaseReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date, end_date = _parse_dates(request)

        qs = Purchase.objects.filter(company=request.user.company, purchase_date__gte=start_date, purchase_date__lte=end_date)
        if request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(created_by=request.user)

        supplier_data = qs.values('supplier__name').annotate(
            total_amount=Sum('total_amount'),
            total_orders=Count('id'),
        ).order_by('-total_amount')

        data = [{'supplier': s['supplier__name'],
                 'total_amount': float(s['total_amount'] or 0),
                 'total_orders': s['total_orders']} for s in supplier_data]

        return api_response(data=data)


# ──────────────────────────────────────────────────────────
# Customer Purchase Report
# ──────────────────────────────────────────────────────────
class CustomerPurchaseReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date, end_date = _parse_dates(request)

        qs = Bill.objects.filter(
            company=request.user.company,
            status='COMPLETED',
            billing_date__date__gte=start_date,
            billing_date__date__lte=end_date,
            customer__isnull=False,
        )
        if request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(cashier=request.user)

        customer_data = qs.values('customer__name', 'customer__phone').annotate(
            total_amount=Sum('grand_total'),
            total_bills=Count('id'),
            last_purchase=Max('billing_date'),
        ).order_by('-total_amount')[:50]

        data = [{'customer': c['customer__name'], 'phone': c['customer__phone'],
                 'total_amount': float(c['total_amount'] or 0),
                 'total_bills': c['total_bills'],
                 'last_purchase': c['last_purchase'].isoformat() if c['last_purchase'] else None
                 } for c in customer_data]

        return api_response(data=data)


# ──────────────────────────────────────────────────────────
# Profit Report
# ──────────────────────────────────────────────────────────
class ProfitReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date, end_date = _parse_dates(request)
        branch_id = request.query_params.get('branch')

        qs = BillItem.objects.filter(
            company=request.user.company,
            bill__status='COMPLETED',
            bill__billing_date__date__gte=start_date,
            bill__billing_date__date__lte=end_date,
        )
        if request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(bill__cashier=request.user)
        if branch_id:
            qs = qs.filter(bill__branch_id=branch_id)

        items = qs.select_related('product')
        total_revenue = Decimal('0')
        total_cost = Decimal('0')
        for item in items:
            total_revenue += item.line_total
            total_cost += item.product.cost_price * item.quantity

        profit = total_revenue - total_cost
        margin = (profit / total_revenue * 100) if total_revenue > 0 else 0

        data = {
            'total_revenue': float(total_revenue),
            'total_cost': float(total_cost),
            'gross_profit': float(profit),
            'profit_margin': round(float(margin), 2),
        }
        return api_response(data=data)


# ──────────────────────────────────────────────────────────
# Stock Valuation Report
# ──────────────────────────────────────────────────────────
class StockValuationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        branch_id = request.query_params.get('branch')
        qs = BranchStock.objects.filter(company=request.user.company, quantity__gt=0).select_related('product', 'branch')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        total_cost_value = Decimal('0')
        total_retail_value = Decimal('0')
        items = []
        for bs in qs:
            cost_val = bs.product.cost_price * bs.quantity
            retail_val = bs.product.selling_price * bs.quantity
            total_cost_value += cost_val
            total_retail_value += retail_val
            items.append({
                'product_name': bs.product.name, 'branch': bs.branch.name,
                'quantity': bs.quantity,
                'cost_value': float(cost_val), 'retail_value': float(retail_val),
            })

        data = {
            'total_cost_value': float(total_cost_value),
            'total_retail_value': float(total_retail_value),
            'potential_profit': float(total_retail_value - total_cost_value),
            'items': items,
        }
        return api_response(data=data)

# ──────────────────────────────────────────────────────────
# Employee Sales Report
# ──────────────────────────────────────────────────────────
class EmployeeSalesReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date, end_date = _parse_dates(request)
        branch_id = request.query_params.get('branch')

        qs = Bill.objects.filter(
            company=request.user.company,
            status='COMPLETED',
            billing_date__date__gte=start_date,
            billing_date__date__lte=end_date,
        )
        if request.user.role_name == 'EMPLOYEE':
            qs = qs.filter(cashier=request.user)
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        employee_data = qs.values('cashier__first_name', 'cashier__last_name', 'cashier__username').annotate(
            total_revenue=Sum('grand_total'),
            total_bills=Count('id'),
            avg_bill=Avg('grand_total'),
        ).order_by('-total_revenue')

        data = []
        for e in employee_data:
            first_name = e['cashier__first_name'] or ''
            last_name = e['cashier__last_name'] or ''
            name = f"{first_name} {last_name}".strip() or e['cashier__username'] or 'Unknown'
            
            data.append({
                 'employee': name,
                 'revenue': float(e['total_revenue'] or 0),
                 'bills': e['total_bills'],
                 'avg_bill': float(e['avg_bill'] or 0)
            })

        return api_response(data=data)
