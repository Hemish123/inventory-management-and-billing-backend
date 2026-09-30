from django.db import models
from django.conf import settings
from django.db import transaction
import datetime


class BillSequence(models.Model):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='bill_sequences')
    branch = models.ForeignKey('core.Branch', on_delete=models.CASCADE)
    date = models.DateField()
    last_number = models.IntegerField(default=0)

    class Meta:
        unique_together = ('company', 'branch', 'date')

    @classmethod
    def next_bill_number(cls, branch):
        today = datetime.date.today()
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(
                company=branch.company, branch=branch, date=today, defaults={'last_number': 0}
            )
            seq.last_number += 1
            seq.save()
        return f"{branch.code}-{today.strftime('%Y%m%d')}-{seq.last_number:04d}"


PAYMENT_METHOD_CHOICES = [
    ('CASH', 'Cash'),
    ('UPI', 'UPI'),
    ('CARD', 'Card'),
    ('NET_BANKING', 'Net Banking'),
    ('CREDIT', 'Credit'),
    ('SPLIT', 'Split Payment'),
]


class Bill(models.Model):
    """POS bill / retail invoice — supports draft, hold, and completed states."""
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('HOLD', 'On Hold'),
        ('COMPLETED', 'Completed'),
        ('RETURNED', 'Returned'),
        ('VOID', 'Void'),
    ]

    DISCOUNT_TYPE_CHOICES = [
        ('NONE', 'No Discount'),
        ('PERCENTAGE', 'Percentage'),
        ('FIXED', 'Fixed Amount'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='bills')
    bill_number = models.CharField(max_length=40, db_index=True)
    branch = models.ForeignKey('core.Branch', on_delete=models.PROTECT, related_name='bills')
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bills', help_text='Walk-in customers = null'
    )
    customer_name = models.CharField(max_length=255, blank=True, default='Walk-in Customer')
    customer_phone = models.CharField(max_length=20, blank=True)

    billing_date = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='DRAFT')

    # Totals
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Overall discount
    discount_type = models.CharField(max_length=12, choices=DISCOUNT_TYPE_CHOICES, default='NONE')
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Round-off
    round_off = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                     help_text='Positive = round up, negative = round down')

    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Payment
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='CASH')
    amount_received = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    change_due = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    notes = models.TextField(blank=True)
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='bills_created'
    )
    salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_made',
        help_text='Sales person selected in POS'
    )

    class Meta:
        ordering = ['-billing_date']
        unique_together = ('company', 'bill_number')
        indexes = [
            models.Index(fields=['status'], name='idx_bill_status'),
            models.Index(fields=['branch', 'status'], name='idx_bill_branch_status'),
        ]

    def __str__(self):
        return f"Bill {self.bill_number}"


class BillItem(models.Model):
    """Individual line item on a bill."""
    DISCOUNT_TYPE_CHOICES = [
        ('NONE', 'No Discount'),
        ('PERCENTAGE', 'Percentage'),
        ('FIXED', 'Fixed Amount'),
    ]

    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='bill_items')
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='bill_items')
    product_name = models.CharField(max_length=255)  # Snapshot at time of sale
    barcode = models.CharField(max_length=50, blank=True)
    hsn_code = models.CharField(max_length=20, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    # Line-item discount
    discount_type = models.CharField(max_length=12, choices=DISCOUNT_TYPE_CHOICES, default='NONE')
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Tax
    tax_percentage = models.IntegerField(default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"


class BillPayment(models.Model):
    """For split payments — stores each payment method + amount on a bill."""
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='bill_payments')
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='payments')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True,
                                  help_text='UPI ref, card last 4 digits, etc.')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_payment_method_display()}: ₹{self.amount}"
