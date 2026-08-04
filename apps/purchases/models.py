from django.db import models
from django.conf import settings


class Purchase(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ORDERED', 'Ordered'),
        ('PARTIAL', 'Partially Received'),
        ('RECEIVED', 'Fully Received'),
        ('CANCELLED', 'Cancelled'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='purchase_orders')
    po_number = models.CharField(max_length=50)
    branch = models.ForeignKey('core.Branch', on_delete=models.PROTECT, related_name='purchases')
    supplier = models.ForeignKey('products.Supplier', on_delete=models.PROTECT, related_name='purchases')
    purchase_date = models.DateField()
    expected_delivery = models.DateField(null=True, blank=True)
    invoice_number = models.CharField(max_length=100, blank=True, help_text='Supplier invoice number')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    gst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='purchases_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-purchase_date']
        unique_together = ('company', 'po_number')

    def __str__(self):
        return f"PO {self.po_number} — {self.supplier.name}"


class PurchaseItem(models.Model):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='purchase_order_items')
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='purchase_items')
    quantity = models.IntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    received_quantity = models.IntegerField(default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_cost
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
