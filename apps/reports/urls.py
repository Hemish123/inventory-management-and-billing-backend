from django.urls import path
from .views import (
    DashboardStatsView, SalesTrendView, SalesReportView,
    PurchaseReportView, InventoryReportView, TopProductsView,
    LowStockView, DeadStockView, BranchSalesReportView,
    SupplierPurchaseReportView, CustomerPurchaseReportView,
    ProfitReportView, StockValuationView,
)

urlpatterns = [
    path('dashboard/', DashboardStatsView.as_view(), name='report-dashboard'),
    path('sales-trend/', SalesTrendView.as_view(), name='report-sales-trend'),
    path('sales/', SalesReportView.as_view(), name='report-sales'),
    path('purchases/', PurchaseReportView.as_view(), name='report-purchases'),
    path('inventory/', InventoryReportView.as_view(), name='report-inventory'),
    path('top-products/', TopProductsView.as_view(), name='report-top-products'),
    path('low-stock/', LowStockView.as_view(), name='report-low-stock'),
    path('dead-stock/', DeadStockView.as_view(), name='report-dead-stock'),
    path('branch-sales/', BranchSalesReportView.as_view(), name='report-branch-sales'),
    path('supplier-purchases/', SupplierPurchaseReportView.as_view(), name='report-supplier-purchases'),
    path('customer-purchases/', CustomerPurchaseReportView.as_view(), name='report-customer-purchases'),
    path('profit/', ProfitReportView.as_view(), name='report-profit'),
    path('stock-valuation/', StockValuationView.as_view(), name='report-stock-valuation'),
]
