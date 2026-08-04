from django.db import models
from django.conf import settings


class StockMovement(models.Model):
    """Atomic log of every stock change. Never deleted — audit trail."""
    MOVEMENT_TYPES = [
        ('IN', 'Stock In'),
        ('OUT', 'Stock Out'),
        ('ADJUSTMENT', 'Adjustment'),
        ('TRANSFER_OUT', 'Transfer Out'),
        ('TRANSFER_IN', 'Transfer In'),
    ]
    REASON_CHOICES = [
        ('PURCHASE', 'Purchase Received'),
        ('SALE', 'Sale'),
        ('RETURN', 'Return'),
        ('DAMAGE', 'Damage / Wastage'),
        ('MANUAL', 'Manual Adjustment'),
        ('TRANSFER', 'Inter-Branch Transfer'),
        ('INITIAL', 'Opening Stock'),
        ('STOCK_COUNT', 'Stock Count Correction'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='stock_movements_logs')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='stock_movements')
    branch = models.ForeignKey('core.Branch', on_delete=models.CASCADE, related_name='stock_movements')
    warehouse = models.ForeignKey(
        'core.Warehouse', on_delete=models.SET_NULL, null=True, blank=True
    )
    movement_type = models.CharField(max_length=15, choices=MOVEMENT_TYPES)
    reason = models.CharField(max_length=15, choices=REASON_CHOICES)
    quantity = models.IntegerField(help_text='Positive for IN, negative for OUT')
    balance_after = models.IntegerField(default=0, help_text='Stock balance after this movement')

    reference_type = models.CharField(max_length=20, blank=True, help_text='bill / purchase / transfer')
    reference_id = models.CharField(max_length=50, blank=True, help_text='Bill number / PO number')
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='stock_movements_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product', 'branch'], name='idx_movement_prod_branch'),
            models.Index(fields=['reference_type', 'reference_id'], name='idx_movement_ref'),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} | {self.product.name} | qty: {self.quantity}"


class StockTransfer(models.Model):
    """Header for an inter-branch stock transfer with full approval workflow."""
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('REQUESTED', 'Requested'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('IN_TRANSIT', 'In Transit'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='stock_transfers')
    transfer_number = models.CharField(max_length=40, blank=True)
    from_branch = models.ForeignKey('core.Branch', on_delete=models.CASCADE, related_name='transfers_out')
    to_branch = models.ForeignKey('core.Branch', on_delete=models.CASCADE, related_name='transfers_in')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(blank=True)
    rejected_reason = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='stock_transfers_created'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_transfers_approved'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('company', 'transfer_number')

    def save(self, *args, **kwargs):
        if not self.transfer_number:
            import datetime
            today = datetime.date.today().strftime('%Y%m%d')
            last = StockTransfer.objects.filter(
                company=self.company,
                transfer_number__startswith=f'TRF-{today}'
            ).count()
            self.transfer_number = f'TRF-{today}-{last + 1:04d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Transfer {self.transfer_number} ({self.from_branch.code} → {self.to_branch.code})"


class StockTransferItem(models.Model):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='stock_transfer_items')
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE)
    quantity = models.IntegerField()
    received_quantity = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
