from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    # Auth
    path('api/auth/', include('apps.authentication.urls')),
    # Core
    path('api/core/', include('apps.core.urls')),
    # Retail modules
    path('api/customers/', include('apps.customers.urls')),
    path('api/products/', include('apps.products.urls')),
    path('api/billing/', include('apps.billing.urls')),
    path('api/stock/', include('apps.stock.urls')),
    path('api/purchases/', include('apps.purchases.urls')),
    path('api/reports/', include('apps.reports.urls')),
]

from django.urls import re_path
from django.views.static import serve

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
