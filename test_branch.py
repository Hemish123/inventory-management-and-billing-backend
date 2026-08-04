import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()
user = User.objects.get(email='demo@msmepaytrack.com')

refresh = RefreshToken.for_user(user)
access_token = str(refresh.access_token)

client = Client(SERVER_NAME='localhost')
response = client.post('/api/core/branches/', {'name': 'Test3', 'code': 'T03'}, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {access_token}')
print(f"Status Code: {response.status_code}")
print(f"Response: {response.content}")
