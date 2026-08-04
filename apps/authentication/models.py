from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """Custom user model for MSME business owners and employees."""
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, null=True, blank=True, related_name='employees')
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, default='')
    
    employee_id = models.CharField(max_length=50, blank=True, default='')
    department = models.CharField(max_length=100, blank=True, default='')
    designation = models.CharField(max_length=100, blank=True, default='')
    
    assigned_branch = models.ForeignKey('core.Branch', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_employees')
    assigned_warehouse = models.ForeignKey('core.Warehouse', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_employees')
    
    role = models.ForeignKey('companies.Role', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    must_change_password = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']

    def __str__(self):
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name} ({self.email})"
        return self.email
