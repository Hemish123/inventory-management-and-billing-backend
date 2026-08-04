import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.companies.models import Company

User = get_user_model()

# Create Company
company, created = Company.objects.get_or_create(
    code='DEMO-001',
    defaults={
        'name': 'Demo Retail Corp',
        'owner_name': 'Demo Owner',
        'email': 'contact@democorp.com',
        'phone': '1234567890'
    }
)
print(f"Company created: {company}")

# Create User
email = 'demo@msmepaytrack.com'
password = 'demo1234'

try:
    user = User.objects.get(email=email)
    user.set_password(password)
    user.company = company
    user.is_superuser = True
    user.is_staff = True
    user.save()
    print(f"User {email} updated.")
except User.DoesNotExist:
    user = User.objects.create_superuser(
        email=email,
        username='demo_user',
        password=password,
        company=company,
        first_name='Demo',
        last_name='Admin'
    )
    print(f"User {email} created.")

