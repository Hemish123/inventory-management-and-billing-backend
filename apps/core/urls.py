from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BranchViewSet, WarehouseViewSet

router = DefaultRouter()
router.register('branches', BranchViewSet, basename='branch')
router.register('warehouses', WarehouseViewSet, basename='warehouse')

urlpatterns = [
    path('', include(router.urls)),
]
