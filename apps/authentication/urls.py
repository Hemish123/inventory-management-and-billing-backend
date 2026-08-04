from django.urls import path
from . import views

from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'employees', views.EmployeeViewSet, basename='employee')

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='auth-register'),
    path('login/', views.LoginView.as_view(), name='auth-login'),
    path('logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('token/refresh/', views.CustomTokenRefreshView.as_view(), name='token-refresh'),
    path('me/', views.MeView.as_view(), name='auth-me'),
    path('delete-account/', views.DeleteAccountView.as_view(), name='auth-delete-account'),
] + router.urls
