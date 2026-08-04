import re

with open('apps/reports/views.py', 'r') as f:
    content = f.read()

# Patch bills_qs in DashboardStatsView
content = re.sub(
    r"(bills_qs = Bill\.objects\.filter\(company=request\.user\.company, status='COMPLETED'\))",
    r"\1\n        if request.user.role_name == 'EMPLOYEE':\n            bills_qs = bills_qs.filter(cashier=request.user)",
    content
)

# Patch pending_purchases in DashboardStatsView
content = re.sub(
    r"(pending_purchases = Purchase\.objects\.filter\([^)]*\)\.count\(\))",
    r"pending_purchases_qs = Purchase.objects.filter(company=request.user.company, status__in=['DRAFT', 'ORDERED', 'PARTIAL'])\n        if request.user.role_name == 'EMPLOYEE':\n            pending_purchases_qs = pending_purchases_qs.filter(created_by=request.user)\n        pending_purchases = pending_purchases_qs.count()",
    content
)

# Patch qs in SalesReportView, SalesTrendView, BranchSalesReportView, CustomerPurchaseReportView
# They all use qs = Bill.objects.filter(...)
content = re.sub(
    r"(qs = Bill\.objects\.filter\([\s\S]*?\n\s*\))",
    r"\1\n        if request.user.role_name == 'EMPLOYEE':\n            qs = qs.filter(cashier=request.user)",
    content
)

# Patch qs in TopProductsView, ProfitReportView (BillItem)
content = re.sub(
    r"(qs = BillItem\.objects\.filter\([\s\S]*?\n\s*\))",
    r"\1\n        if request.user.role_name == 'EMPLOYEE':\n            qs = qs.filter(bill__cashier=request.user)",
    content
)

# Patch qs in PurchaseReportView, SupplierPurchaseReportView (Purchase)
content = re.sub(
    r"(qs = Purchase\.objects\.filter\([^\)]*\))",
    r"\1\n        if request.user.role_name == 'EMPLOYEE':\n            qs = qs.filter(created_by=request.user)",
    content
)

with open('apps/reports/views.py', 'w') as f:
    f.write(content)
