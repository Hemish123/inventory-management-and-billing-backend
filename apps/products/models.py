from django.db import models
from django.conf import settings
import random
import string


class Category(models.Model):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Brand(models.Model):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='brands')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Supplier(models.Model):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='suppliers')
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    gstin = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


def generate_barcode():
    """Generate a unique 12-digit barcode."""
    return ''.join(random.choices(string.digits, k=12))


class Product(models.Model):
    UNIT_CHOICES = [
        ('Nos', 'Numbers'), ('Kg', 'Kilograms'), ('Ltr', 'Litres'),
        ('Mtr', 'Metres'), ('Box', 'Box'), ('Pcs', 'Pieces'),
        ('Set', 'Set'), ('Pair', 'Pair'), ('Dozen', 'Dozen'),
        ('Packets', 'Packets'), ('Cartoon', 'Cartoon'),
        ('Other', 'Other'),
    ]

    # Identity
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='products')
    sku = models.CharField(max_length=100, blank=True, db_index=True)
    barcode = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Classification
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)

    # Pricing
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='Nos')
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Tax
    hsn_code = models.CharField(max_length=20, blank=True)
    tax_percentage = models.IntegerField(default=0, help_text='GST %')

    # Stock (global, aggregated from BranchStock)
    minimum_stock_level = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=0, help_text='Suggest reorder when stock falls below')

    # Dead stock tracking
    dead_stock_days = models.IntegerField(default=0, help_text='Mark as dead stock if no sale in this many days')

    # Image
    image = models.ImageField(upload_to='product_images/', null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('company', 'barcode')

    def save(self, *args, **kwargs):
        if not self.barcode:
            for _ in range(10):
                code = generate_barcode()
                if not Product.objects.filter(company=self.company, barcode=code).exists():
                    self.barcode = code
                    break
        super().save(*args, **kwargs)

    @property
    def total_stock(self):
        """Sum of stock across all branches."""
        if hasattr(self, '_total_stock_annotated'):
            return self._total_stock_annotated
        return self.branch_stocks.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0

    @total_stock.setter
    def total_stock(self, value):
        self._total_stock_annotated = value

    def __str__(self):
        return f"{self.name} ({self.sku or self.barcode})"


class BranchStock(models.Model):
    """Stock quantity of a product at a specific branch+warehouse."""
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='branch_stock_entries')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='branch_stocks')
    branch = models.ForeignKey('core.Branch', on_delete=models.CASCADE, related_name='stock_entries')
    warehouse = models.ForeignKey(
        'core.Warehouse', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_entries'
    )
    quantity = models.IntegerField(default=0)

    class Meta:
        unique_together = ('product', 'branch', 'warehouse')

    def __str__(self):
        wh = f" / {self.warehouse.name}" if self.warehouse else ""
        return f"{self.product.name} @ {self.branch.name}{wh}: {self.quantity}"
