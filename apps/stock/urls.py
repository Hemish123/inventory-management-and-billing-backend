from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StockMovementViewSet, StockTransferViewSet

router = DefaultRouter()
router.register('movements', StockMovementViewSet, basename='stockmovement')
router.register('transfers', StockTransferViewSet, basename='stocktransfer')

urlpatterns = [
    path('', include(router.urls)),
]
