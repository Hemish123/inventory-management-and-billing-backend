from django.db import models
from django.conf import settings


class Company(models.Model):
    """
    Represents a tenant in the multi-tenant system.
    Every company has completely isolated data.
    """
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, unique=True, help_text="Auto-generated unique company code")
    gst_number = models.CharField(max_length=50, blank=True, default='')
    business_type = models.CharField(max_length=100, blank=True, default='')
    owner_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    
    # Address
    address = models.TextField(blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, blank=True, default='')
    country = models.CharField(max_length=100, blank=True, default='India')
    pincode = models.CharField(max_length=20, blank=True, default='')
    
    # Settings
    logo = models.ImageField(upload_to='company_logos/', null=True, blank=True)
    time_zone = models.CharField(max_length=100, default='Asia/Kolkata')
    currency = models.CharField(max_length=10, default='INR')
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Companies'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Permission(models.Model):
    """
    Granular permissions for RBAC.
    """
    module = models.CharField(max_length=50, help_text="e.g., Inventory, Billing, Users")
    name = models.CharField(max_length=100, help_text="e.g., View Products, Create Invoice")
    codename = models.CharField(max_length=100, unique=True, help_text="e.g., view_products, create_invoice")

    class Meta:
        ordering = ['module', 'name']

    def __str__(self):
        return f"{self.module} - {self.name}"


class Role(models.Model):
    """
    User roles for RBAC. 
    Can be default (company=None) or custom per company.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='roles')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    is_default = models.BooleanField(default=False, help_text="Is this a system default role?")
    permissions = models.ManyToManyField(Permission, blank=True, related_name='roles')

    class Meta:
        unique_together = ('company', 'name')
        ordering = ['name']

    def __str__(self):
        if self.company:
            return f"{self.name} ({self.company.name})"
        return f"{self.name} (System Default)"


class AuditLog(models.Model):
    """
    Tracks all user activity for accountability.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=255)
    module = models.CharField(max_length=50, blank=True, default='')
    details = models.TextField(blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    browser = models.CharField(max_length=255, blank=True, default='')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} by {self.user} at {self.timestamp}"
