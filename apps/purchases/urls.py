from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PurchaseViewSet, ExpenseViewSet

router = DefaultRouter()
router.register('expenses', ExpenseViewSet, basename='expense')
router.register('', PurchaseViewSet, basename='purchase')

urlpatterns = [
    path('', include(router.urls)),
]
