from django.db import models


class Branch(models.Model):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    manager_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Branches'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Warehouse(models.Model):
    company = models.ForeignKey('companies.Company', on_delete=models.CASCADE, related_name='warehouses')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='warehouses')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20)
    location_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('branch', 'code')
        ordering = ['branch', 'name']

    def __str__(self):
        return f"{self.name} @ {self.branch.name}"
