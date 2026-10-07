from django.db import models
from django.conf import settings


class Customer(models.Model):
    """Retail customer — simplified for POS billing."""
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    address = models.TextField(blank=True, default='')
    gstin = models.CharField(max_length=15, blank=True, default='', verbose_name='GSTIN')
    company_name = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='customers'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='customers_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ['name', 'company']

    def __str__(self):
        return f"{self.name} ({self.company_name})" if self.company_name else self.name
