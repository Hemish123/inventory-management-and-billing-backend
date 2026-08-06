from apps.core.mixins import TenantMixin
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from utils.response import api_response, api_error
from .models import Category, Brand, Supplier, Product, BranchStock
from .serializers import (
    CategorySerializer, BrandSerializer, SupplierSerializer,
    ProductSerializer, ProductListSerializer, ProductDropdownSerializer,
    BranchStockSerializer,
)
import io
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.graphics.barcode import createBarcodeDrawing


class CategoryViewSet(TenantMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(is_active=True)
    search_fields = ['name']

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return api_response(data=serializer.data, message='Category created',
                                status_code=status.HTTP_201_CREATED)
        return api_error(errors=serializer.errors)


class BrandViewSet(TenantMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = BrandSerializer
    queryset = Brand.objects.filter(is_active=True)
    search_fields = ['name']

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return api_response(data=serializer.data, message='Brand created',
                                status_code=status.HTTP_201_CREATED)
        return api_error(errors=serializer.errors)


class SupplierViewSet(TenantMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SupplierSerializer
    queryset = Supplier.objects.filter(is_active=True)
    search_fields = ['name', 'contact_person', 'email', 'gstin']

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return api_response(data=serializer.data, message='Supplier created',
                                status_code=status.HTTP_201_CREATED)
        return api_error(errors=serializer.errors)


class ProductViewSet(TenantMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Product.objects.all()
    search_fields = ['name', 'sku', 'barcode', 'hsn_code']
    ordering_fields = ['name', 'selling_price', 'created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductSerializer

    def get_queryset(self):
        qs = super().get_queryset().filter(is_active=True).select_related(
            'category', 'brand', 'supplier'
        ).annotate(
            total_stock=Sum('branch_stocks__quantity')
        )
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category_id=category)
        supplier = self.request.query_params.get('supplier')
        if supplier:
            qs = qs.filter(supplier_id=supplier)
        low_stock = self.request.query_params.get('low_stock')
        if low_stock == 'true':
            from django.db.models import F
            qs = qs.filter(total_stock__lt=F('minimum_stock_level'))
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)

        # Handle Category creation on the fly
        category_name = data.get('category')
        if category_name and not str(category_name).isdigit():
            cat, _ = Category.objects.get_or_create(
                name=category_name, company=request.user.company,
                defaults={'description': ''}
            )
            data['category'] = cat.id

        # Handle Brand creation on the fly
        brand_name = data.get('brand')
        if brand_name and not str(brand_name).isdigit():
            brand, _ = Brand.objects.get_or_create(
                name=brand_name, company=request.user.company,
                defaults={'description': ''}
            )
            data['brand'] = brand.id

        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return api_response(data=serializer.data, message='Product created',
                                status_code=status.HTTP_201_CREATED)
        return api_error(errors=serializer.errors)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)

        category_name = data.get('category')
        if category_name and not str(category_name).isdigit():
            cat, _ = Category.objects.get_or_create(
                name=category_name, company=request.user.company,
                defaults={'description': ''}
            )
            data['category'] = cat.id

        brand_name = data.get('brand')
        if brand_name and not str(brand_name).isdigit():
            brand, _ = Brand.objects.get_or_create(
                name=brand_name, company=request.user.company,
                defaults={'description': ''}
            )
            data['brand'] = brand.id

        serializer = self.get_serializer(instance, data=data, partial=partial)
        if serializer.is_valid():
            self.perform_update(serializer)
            return api_response(data=serializer.data, message='Product updated')
        return api_error(errors=serializer.errors)

    @action(detail=False, methods=['get'], url_path='dropdown')
    def dropdown(self, request):
        products = self.get_queryset().order_by('name')
        serializer = ProductDropdownSerializer(products, many=True)
        return api_response(data=serializer.data)

    @action(detail=True, methods=['get'], url_path='stock')
    def stock(self, request, pk=None):
        product = self.get_object()
        stocks = BranchStock.objects.filter(product=product).select_related('branch', 'warehouse')
        serializer = BranchStockSerializer(stocks, many=True)
        return api_response(data=serializer.data)

    @action(detail=False, methods=['get'], url_path='barcode-lookup')
    def barcode_lookup(self, request):
        barcode = request.query_params.get('code', '')
        if not barcode:
            return api_error(message='Barcode is required')
        try:
            product = self.get_queryset().get(barcode=barcode)
            serializer = ProductSerializer(product)
            return api_response(data=serializer.data)
        except Product.DoesNotExist:
            return api_error(message='Product not found', status_code=404)

    @action(detail=False, methods=['post'], url_path='print-barcodes')
    def print_barcodes(self, request):
        items = request.data.get('items', [])
        if not items:
            return api_error(message='No items provided for barcode printing.')

        # Extract product ids and quantities
        product_qtys = {}
        for item in items:
            product_id = item.get('product_id') or item.get('id')
            qty = int(item.get('quantity', 1))
            if product_id:
                product_qtys[product_id] = product_qtys.get(product_id, 0) + qty

        products = self.get_queryset().filter(id__in=product_qtys.keys())
        
        # Flatten items based on quantity
        print_items = []
        for p in products:
            qty = product_qtys.get(p.id, 0)
            for _ in range(qty):
                print_items.append(p)

        if not print_items:
            return api_error(message='No valid products found.')

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        cols = 3
        rows = 7
        labels_per_page = cols * rows
        
        label_w = width / cols
        label_h = height / rows
        
        for i, p in enumerate(print_items):
            if i > 0 and i % labels_per_page == 0:
                c.showPage()
                
            pos_in_page = i % labels_per_page
            r = pos_in_page // cols
            col = pos_in_page % cols
            
            x = col * label_w
            y = height - ((r + 1) * label_h)
            
            center_x = x + (label_w / 2.0)
            
            # Draw Product Name
            c.setFont("Helvetica", 10)
            name = (p.name[:30] + '..') if len(p.name) > 30 else p.name
            c.drawCentredString(center_x, y + label_h - 20, name)
            
            # Draw Barcode
            try:
                barcode_value = p.barcode if p.barcode else p.sku
                if barcode_value:
                    barcode = createBarcodeDrawing('Code128', value=barcode_value, width=label_w - 40, height=label_h - 60, humanReadable=True)
                    b_x = x + (label_w - barcode.width) / 2
                    b_y = y + 25
                    barcode.drawOn(c, b_x, b_y)
            except Exception:
                pass
            
            # Draw Price
            c.setFont("Helvetica-Bold", 12)
            c.drawCentredString(center_x, y + 10, f"₹{p.selling_price}")
            
        c.save()
        buffer.seek(0)
        
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="barcodes.pdf"'
        return response
