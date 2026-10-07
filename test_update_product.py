import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.products.models import Product, Supplier

supplier, _ = Supplier.objects.get_or_create(name="Test Supplier Auto", company_id=1)
print("Supplier ID:", supplier.id)

product = Product.objects.first()
print("Product ID:", product.id, "Current Supplier:", product.supplier)

from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.first()
client = APIClient()
client.force_authenticate(user=user)

# Update product with supplier ID
response = client.put('/api/products/{}/'.format(product.id), {'name': product.name, 'supplier': supplier.id}, format='json')
print("Status Code:", response.status_code)
print("Response Data:", response.data)

product.refresh_from_db()
print("Updated Product Supplier:", product.supplier)

