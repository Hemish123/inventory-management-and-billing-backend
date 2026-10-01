from apps.core.mixins import TenantMixin
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
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
import io, os, json, logging
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.graphics.barcode import createBarcodeDrawing

logger = logging.getLogger(__name__)


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

    @action(detail=False, methods=['get'], url_path='dead-stock')
    def dead_stock(self, request):
        """List products that have not been sold within their dead_stock_days threshold."""
        from django.utils import timezone
        from apps.billing.models import BillItem
        from django.db.models import Max, F, Value, IntegerField
        from datetime import timedelta

        products = self.get_queryset()

        # Annotate each product with its last sale date from completed bills
        products = products.annotate(
            last_sold_date=Max(
                'bill_items__bill__billing_date',
                filter=models.Q(bill_items__bill__status='COMPLETED')
            )
        )

        now = timezone.now()
        dead_products = []
        for p in products:
            threshold_date = now - timedelta(days=p.dead_stock_days)
            if p.last_sold_date is None or p.last_sold_date < threshold_date:
                dead_products.append({
                    'id': p.id,
                    'name': p.name,
                    'barcode': p.barcode,
                    'sku': p.sku,
                    'category_name': p.category.name if p.category else '',
                    'selling_price': str(p.selling_price),
                    'cost_price': str(p.cost_price),
                    'total_stock': p.total_stock or 0,
                    'dead_stock_days': p.dead_stock_days,
                    'last_sold_date': p.last_sold_date.isoformat() if p.last_sold_date else None,
                    'days_since_last_sale': (now - p.last_sold_date).days if p.last_sold_date else None,
                })

        return api_response(data=dead_products)

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
        """Generate barcode PDF for NJ MPL sticker sheets (l40, l16, l110, l48)."""
        items = request.data.get('items', [])
        if not items:
            return api_error(message='No items provided for barcode printing.')

        # Determine sticker-sheet format (default l48)
        size_key = request.data.get('size', 'l48')

        # Get company name for marketing
        company_name = ''
        if hasattr(request.user, 'company') and request.user.company:
            company_name = request.user.company.name

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

        from reportlab.lib.units import mm
        from reportlab.pdfbase.pdfmetrics import stringWidth

        # ── NJ MPL sticker-sheet configurations (all values in mm) ──
        SIZE_CONFIGS = {
            'l48': {
                'cols': 4, 'rows': 12, 'labelW': 48, 'labelH': 24, 'gapX': 2, 'gapY': 0.25,
                'marginTop': 1.125, 'marginLeft': 8,
                'padTop': 1, 'padBottom': 1, 'padLeft': 1.5, 'padRight': 1.5,
                'barcodeW': 38, 'barcodeH': 9,
                'companyFont': 6, 'companyBoxH': 3,
                'digitsFont': 6.5, 'digitsBoxH': 3,
                'nameFont': 7, 'priceFont': 9, 'bottomRowH': 4.5,
                'showCompany': True, 'showName': True, 'showPrice': True,
                'layout': 'vertical',
            },
            'l16': {
                'cols': 2, 'rows': 8, 'labelW': 99, 'labelH': 34, 'gapX': 2, 'gapY': 1.28,
                'marginTop': 2.52, 'marginLeft': 4,
                'padTop': 2, 'padBottom': 2, 'padLeft': 2, 'padRight': 2,
                'leftColW': 50, 'rightColW': 43,
                'barcodeW': 46, 'barcodeH': 15,
                'digitsFont': 8, 'digitsBoxH': 4,
                'companyFont': 8, 'companyBoxH': 4,
                'nameFont': 10, 'nameBoxH': 8,
                'priceFont': 16, 'priceBoxH': 8,
                'showCompany': True, 'showName': True, 'showPrice': True,
                'layout': 'horizontal',
            },
            'l40': {
                'cols': 10, 'rows': 4, 'labelW': 18, 'labelH': 73, 'gapX': 1, 'gapY': 1,
                'marginTop': 1.5, 'marginLeft': 1.5,
                'padTop': 1.5, 'padBottom': 1.5, 'padLeft': 1.5, 'padRight': 1.5,
                'barcodeW': 55, 'barcodeH': 6,
                'companyFont': 5.5, 'companyBoxH': 2.4,
                'digitsFont': 6, 'digitsBoxH': 2.4,
                'nameFont': 7, 'priceFont': 9, 'bottomRowH': 3.6,
                'showCompany': True, 'showName': True, 'showPrice': True,
                'layout': 'rotated',
            },
            'l110': {
                'cols': 5, 'rows': 22, 'labelW': 35, 'labelH': 10, 'gapX': 2, 'gapY': 2.5,
                'marginTop': 12.25, 'marginLeft': 7.5,
                'padTop': 0.5, 'padBottom': 0.5, 'padLeft': 0.5, 'padRight': 0.5,
                'barcodeW': 24, 'barcodeH': 4.5,
                'digitsFont': 5, 'digitsBoxH': 2,
                'nameFont': 5, 'nameBoxH': 2.2,
                'priceFont': 8, 'priceColW': 10,
                'showCompany': False, 'showName': True, 'showPrice': True,
                'layout': 'tiny',
            },
        }

        cfg = SIZE_CONFIGS.get(size_key, SIZE_CONFIGS['l48'])
        cols = cfg['cols']
        rows = cfg['rows']
        label_w = cfg['labelW'] * mm
        label_h = cfg['labelH'] * mm
        gap_x = cfg['gapX'] * mm
        gap_y = cfg['gapY'] * mm
        margin_top = cfg['marginTop'] * mm
        margin_left = cfg['marginLeft'] * mm
        labels_per_page = cols * rows
        layout = cfg['layout']

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        page_w, page_h = A4

        def truncate_text(text, font_name, font_size, max_width):
            if not text: return ""
            text = str(text)
            if stringWidth(text, font_name, font_size) <= max_width:
                return text
            while len(text) > 0 and stringWidth(text + "..", font_name, font_size) > max_width:
                text = text[:-1]
            return text + ".."

        # Helper to draw barcode properly scaled and centered in its bounding box
        def draw_barcode(x, y, w_mm, h_mm, value):
            if not value: return
            fmt = 'Code128Auto' if value.isdigit() and len(value) % 2 == 0 else 'Code128'
            from reportlab.graphics.barcode.code128 import Code128Auto, Code128
            try:
                bc_class = Code128Auto if fmt == 'Code128Auto' else Code128
                bc = bc_class(value=value, barHeight=h_mm * mm, humanReadable=False)
                natural_width = bc.width
                scale = (w_mm * mm) / natural_width
                bc.barWidth = bc.barWidth * scale
                bc.drawOn(c, x, y)
            except Exception as e:
                logger.error(f"Failed to generate barcode: {e}")

        for i, p in enumerate(print_items):
            if i > 0 and i % labels_per_page == 0:
                c.showPage()

            pos = i % labels_per_page
            r = pos // cols
            col_idx = pos % cols

            x = margin_left + col_idx * (label_w + gap_x)
            y = page_h - margin_top - (r + 1) * label_h - r * gap_y
            
            barcode_value = p.barcode if p.barcode else p.sku

            if layout == 'vertical': # l48
                cx = x + label_w / 2.0
                curr_y = y + label_h - cfg['padTop'] * mm
                
                # Company
                if cfg['showCompany'] and company_name:
                    c.setFont("Helvetica-Bold", cfg['companyFont'])
                    co = truncate_text(company_name.upper(), "Helvetica-Bold", cfg['companyFont'], (cfg['labelW'] - cfg['padLeft'] - cfg['padRight']) * mm)
                    curr_y -= cfg['companyBoxH'] * mm
                    c.drawCentredString(cx, curr_y + (cfg['companyBoxH']*mm - cfg['companyFont'])/2.0, co)
                
                # Barcode
                curr_y -= cfg['barcodeH'] * mm
                bc_x = x + (cfg['labelW'] - cfg['barcodeW']) * mm / 2.0
                draw_barcode(bc_x, curr_y, cfg['barcodeW'], cfg['barcodeH'], barcode_value)
                
                # Digits
                curr_y -= cfg['digitsBoxH'] * mm
                if barcode_value:
                    c.setFont("Helvetica", cfg['digitsFont'])
                    c.drawCentredString(cx, curr_y + (cfg['digitsBoxH']*mm - cfg['digitsFont'])/2.0, barcode_value)
                
                # Name & Price
                curr_y -= cfg['bottomRowH'] * mm
                usable_w = (cfg['labelW'] - cfg['padLeft'] - cfg['padRight']) * mm
                price_str = f"₹{p.selling_price}"
                c.setFont("Helvetica-Bold", cfg['priceFont'])
                price_w = stringWidth(price_str, "Helvetica-Bold", cfg['priceFont'])
                
                if cfg['showName']:
                    name_max_w = usable_w - price_w - 2 * mm
                    c.setFont("Helvetica-Bold", cfg['nameFont'])
                    name_str = truncate_text(p.name, "Helvetica-Bold", cfg['nameFont'], name_max_w)
                    c.drawString(x + cfg['padLeft'] * mm, curr_y + (cfg['bottomRowH']*mm - cfg['nameFont'])/2.0, name_str)
                
                if cfg['showPrice']:
                    c.setFont("Helvetica-Bold", cfg['priceFont'])
                    c.drawString(x + cfg['labelW']*mm - cfg['padRight']*mm - price_w, curr_y + (cfg['bottomRowH']*mm - cfg['priceFont'])/2.0, price_str)
            
            elif layout == 'horizontal': # l16
                # Left Column (Barcode)
                left_x = x + cfg['padLeft'] * mm
                cy_left = y + label_h / 2.0
                
                bc_x = left_x + (cfg['leftColW'] - cfg['barcodeW']) * mm / 2.0
                bc_y = cy_left - (cfg['barcodeH'] + cfg['digitsBoxH']) * mm / 2.0 + cfg['digitsBoxH'] * mm
                draw_barcode(bc_x, bc_y, cfg['barcodeW'], cfg['barcodeH'], barcode_value)
                
                if barcode_value:
                    c.setFont("Helvetica", cfg['digitsFont'])
                    c.drawCentredString(left_x + cfg['leftColW'] * mm / 2.0, bc_y - cfg['digitsBoxH'] * mm + (cfg['digitsBoxH']*mm - cfg['digitsFont'])/2.0, barcode_value)
                
                # Right Column (Text)
                right_x = x + cfg['padLeft'] * mm + cfg['leftColW'] * mm + 2 * mm
                right_w = (cfg['rightColW'] - 2) * mm
                curr_y = y + label_h - cfg['padTop'] * mm - 2 * mm # extra padding
                
                if cfg['showCompany'] and company_name:
                    curr_y -= cfg['companyBoxH'] * mm
                    c.setFont("Helvetica-Bold", cfg['companyFont'])
                    co = truncate_text(company_name.upper(), "Helvetica-Bold", cfg['companyFont'], right_w)
                    c.drawString(right_x, curr_y + (cfg['companyBoxH']*mm - cfg['companyFont'])/2.0, co)
                
                if cfg['showName']:
                    curr_y -= cfg['nameBoxH'] * mm
                    c.setFont("Helvetica-Bold", cfg['nameFont'])
                    name_str = truncate_text(p.name, "Helvetica-Bold", cfg['nameFont'], right_w * 2) # Allow 2 lines approx
                    # Simplistic 2 line split
                    words = name_str.split()
                    line1 = ""
                    line2 = ""
                    for w in words:
                        if stringWidth(line1 + " " + w, "Helvetica-Bold", cfg['nameFont']) < right_w:
                            line1 += " " + w if line1 else w
                        else:
                            line2 += " " + w if line2 else w
                    if stringWidth(line2, "Helvetica-Bold", cfg['nameFont']) > right_w:
                        line2 = truncate_text(line2, "Helvetica-Bold", cfg['nameFont'], right_w)
                    
                    c.drawString(right_x, curr_y + cfg['nameBoxH'] * mm / 2.0, line1)
                    if line2:
                        c.drawString(right_x, curr_y, line2)
                
                if cfg['showPrice']:
                    curr_y -= cfg['priceBoxH'] * mm
                    c.setFont("Helvetica-Bold", cfg['priceFont'])
                    c.drawString(right_x, curr_y + (cfg['priceBoxH']*mm - cfg['priceFont'])/2.0, f"₹{p.selling_price}")
            
            elif layout == 'tiny': # l110
                usable_w = (cfg['labelW'] - cfg['padLeft'] - cfg['padRight']) * mm
                curr_y = y + label_h - cfg['padTop'] * mm
                
                if cfg['showName']:
                    curr_y -= cfg['nameBoxH'] * mm
                    c.setFont("Helvetica-Bold", cfg['nameFont'])
                    name_str = truncate_text(p.name, "Helvetica-Bold", cfg['nameFont'], usable_w)
                    c.drawString(x + cfg['padLeft'] * mm, curr_y + (cfg['nameBoxH']*mm - cfg['nameFont'])/2.0, name_str)
                
                # Bottom Row: barcode left, price right
                bottom_y = curr_y - cfg['barcodeH'] * mm - cfg['digitsBoxH'] * mm
                draw_barcode(x + cfg['padLeft'] * mm, bottom_y + cfg['digitsBoxH'] * mm, cfg['barcodeW'], cfg['barcodeH'], barcode_value)
                
                if barcode_value:
                    c.setFont("Helvetica", cfg['digitsFont'])
                    c.drawCentredString(x + cfg['padLeft'] * mm + cfg['barcodeW'] * mm / 2.0, bottom_y + (cfg['digitsBoxH']*mm - cfg['digitsFont'])/2.0, barcode_value)
                
                if cfg['showPrice']:
                    price_str = f"₹{p.selling_price}"
                    c.setFont("Helvetica-Bold", cfg['priceFont'])
                    price_w = stringWidth(price_str, "Helvetica-Bold", cfg['priceFont'])
                    price_x = x + cfg['labelW'] * mm - cfg['padRight'] * mm - price_w
                    price_y_center = bottom_y + (cfg['barcodeH'] + cfg['digitsBoxH']) * mm / 2.0 - cfg['priceFont']/2.0
                    c.drawString(price_x, price_y_center, price_str)
            
            elif layout == 'rotated': # l40
                c.saveState()
                # Translate to bottom-left of the cell, then translate to W and rotate 90.
                c.translate(x, y)
                c.translate(label_w, 0)
                c.rotate(90)
                
                # Now we draw in a space where width = 73mm, height = 18mm
                r_w = cfg['labelH'] * mm
                r_h = cfg['labelW'] * mm
                
                cx = r_w / 2.0
                curr_y = r_h - cfg['padTop'] * mm
                
                if cfg['showCompany'] and company_name:
                    c.setFont("Helvetica-Bold", cfg['companyFont'])
                    co = truncate_text(company_name.upper(), "Helvetica-Bold", cfg['companyFont'], (cfg['labelH'] - cfg['padLeft'] - cfg['padRight']) * mm)
                    curr_y -= cfg['companyBoxH'] * mm
                    c.drawCentredString(cx, curr_y + (cfg['companyBoxH']*mm - cfg['companyFont'])/2.0, co)
                
                curr_y -= cfg['barcodeH'] * mm
                bc_x = (r_w - cfg['barcodeW'] * mm) / 2.0
                draw_barcode(bc_x, curr_y, cfg['barcodeW'], cfg['barcodeH'], barcode_value)
                
                curr_y -= cfg['digitsBoxH'] * mm
                if barcode_value:
                    c.setFont("Helvetica", cfg['digitsFont'])
                    c.drawCentredString(cx, curr_y + (cfg['digitsBoxH']*mm - cfg['digitsFont'])/2.0, barcode_value)
                
                curr_y -= cfg['bottomRowH'] * mm
                usable_w = (cfg['labelH'] - cfg['padLeft'] - cfg['padRight']) * mm
                price_str = f"₹{p.selling_price}"
                c.setFont("Helvetica-Bold", cfg['priceFont'])
                price_w = stringWidth(price_str, "Helvetica-Bold", cfg['priceFont'])
                
                if cfg['showName']:
                    name_max_w = usable_w - price_w - 2 * mm
                    c.setFont("Helvetica-Bold", cfg['nameFont'])
                    name_str = truncate_text(p.name, "Helvetica-Bold", cfg['nameFont'], name_max_w)
                    c.drawString(cfg['padLeft'] * mm, curr_y + (cfg['bottomRowH']*mm - cfg['nameFont'])/2.0, name_str)
                
                if cfg['showPrice']:
                    c.setFont("Helvetica-Bold", cfg['priceFont'])
                    c.drawString(r_w - cfg['padRight'] * mm - price_w, curr_y + (cfg['bottomRowH']*mm - cfg['priceFont'])/2.0, price_str)
                
                c.restoreState()

        c.save()
        buffer.seek(0)

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="barcodes.pdf"'
        return response

    @action(detail=False, methods=['post'], url_path='upload-pdf',
            parser_classes=[MultiPartParser, FormParser])
    def upload_pdf(self, request):
        """Extract products from an uploaded PDF using OpenAI GPT-4o-mini."""
        pdf_file = request.FILES.get('file')
        if not pdf_file:
            return api_error(message='No PDF file provided.')

        if not pdf_file.name.lower().endswith('.pdf'):
            return api_error(message='Only PDF files are accepted.')

        # --- 1. Extract text & images from PDF ---
        try:
            import fitz  # PyMuPDF
            import base64
            pdf_bytes = pdf_file.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_parts = []
            base64_images = []
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
                else:
                    # Fallback to image for scanned pages
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("jpeg")
                    base64_images.append(base64.b64encode(img_bytes).decode('utf-8'))
            doc.close()
            pdf_text = "\n".join(text_parts).strip()
        except Exception as e:
            logger.exception("PDF extraction failed")
            return api_error(message=f'Failed to read PDF: {str(e)}')

        if not pdf_text and not base64_images:
            return api_error(message='No readable text or images found in the PDF.')

        # --- 2. Send to OpenAI GPT-4o-mini ---
        # from openai import OpenAI
        # api_key = os.environ.get('OPENAI_API_KEY', '')
        # if not api_key:
        #     return api_error(message='OpenAI API key is not configured on the server.')
        
        from openai import AzureOpenAI
        azure_endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT', 'https://jivihireopenai.openai.azure.com')
        azure_api_key = os.environ.get('AZURE_OPENAI_KEY', '')
        azure_deployment = os.environ.get('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o-mini')
        azure_api_version = os.environ.get('AZURE_OPENAI_API_VERSION', '2024-05-01-preview')

        if not azure_api_key:
            return api_error(message='Azure OpenAI API key is not configured on the server.')

        prompt_text = (
            "You are a product data extractor. Analyze the following text/images extracted from a PDF "
            "and return a JSON array of product objects. Each product object should have these fields "
            "(use empty string or 0 for missing values):\n"
            "- name (string, required)\n"
            "- sku (string)\n"
            "- description (string)\n"
            "- category (string)\n"
            "- brand (string)\n"
            "- unit (string, one of: Nos, Kg, Ltr, Mtr, Box, Pcs, Set, Pair, Dozen, Other)\n"
            "- cost_price (number)\n"
            "- selling_price (number)\n"
            "- hsn_code (string)\n"
            "- tax_percentage (number, typically 0, 5, 12, 18, or 28)\n"
            "\nReturn ONLY a valid JSON array, no markdown, no explanation.\n"
        )
        
        user_content = [{"type": "text", "text": prompt_text}]
        if pdf_text:
            user_content[0]["text"] += f"\n\nPDF TEXT:\n{pdf_text[:15000]}"
            
        for b64_img in base64_images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
            })

        try:
            # client = OpenAI(api_key=api_key)
            # completion = client.chat.completions.create(
            #     model="gpt-4o-mini",
            #     messages=[
            #         {"role": "system", "content": "You extract structured product data from text and images. Always respond with valid JSON only."},
            #         {"role": "user", "content": user_content}
            #     ],
            #     temperature=0.1,
            #     max_tokens=4096,
            # )
            client = AzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=azure_api_key,
                api_version=azure_api_version
            )
            completion = client.chat.completions.create(
                model=azure_deployment,
                messages=[
                    {"role": "system", "content": "You extract structured product data from text and images. Always respond with valid JSON only."},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            ai_text = completion.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if ai_text.startswith("```"):
                ai_text = ai_text.split("\n", 1)[1] if "\n" in ai_text else ai_text[3:]
                if ai_text.endswith("```"):
                    ai_text = ai_text[:-3]
                ai_text = ai_text.strip()
            products_data = json.loads(ai_text)
        except json.JSONDecodeError:
            logger.error("OpenAI returned non-JSON: %s", ai_text[:500])
            return api_error(message='AI returned invalid data. Please try a cleaner PDF.')
        except Exception as e:
            logger.exception("OpenAI API call failed")
            return api_error(message=f'AI processing failed: {str(e)}')

        if not isinstance(products_data, list) or len(products_data) == 0:
            return api_error(message='No products could be extracted from the PDF.')

        # --- 3. Bulk-create products (duplicates allowed) ---
        company = request.user.company
        created = []
        for item in products_data:
            try:
                cat_name = str(item.get('category', '')).strip()
                cat = None
                if cat_name:
                    cat, _ = Category.objects.get_or_create(
                        name=cat_name, company=company, defaults={'description': ''})

                brand_name = str(item.get('brand', '')).strip()
                brand = None
                if brand_name:
                    brand, _ = Brand.objects.get_or_create(
                        name=brand_name, company=company, defaults={'description': ''})

                product = Product(
                    company=company,
                    name=str(item.get('name', 'Unnamed Product')).strip(),
                    sku=str(item.get('sku', '')).strip(),
                    description=str(item.get('description', '')).strip(),
                    category=cat,
                    brand=brand,
                    unit=str(item.get('unit', 'Nos')).strip() or 'Nos',
                    cost_price=float(item.get('cost_price', 0) or 0),
                    selling_price=float(item.get('selling_price', 0) or 0),
                    hsn_code=str(item.get('hsn_code', '')).strip(),
                    tax_percentage=int(item.get('tax_percentage', 18) or 18),
                )
                product.save()  # auto-generates unique barcode
                created.append({
                    'id': product.id,
                    'name': product.name,
                    'sku': product.sku,
                    'barcode': product.barcode,
                    'description': product.description,
                    'category': product.category_id,
                    'category_name': cat.name if cat else '',
                    'brand': product.brand_id,
                    'brand_name': brand.name if brand else '',
                    'unit': product.unit,
                    'cost_price': str(product.cost_price),
                    'selling_price': str(product.selling_price),
                    'hsn_code': product.hsn_code,
                    'tax_percentage': product.tax_percentage,
                })
            except Exception as e:
                logger.warning("Failed to create product from PDF item: %s — %s", item, e)
                continue

        if not created:
            return api_error(message='Failed to create any products from the PDF.')

        return api_response(
            data={'products': created, 'count': len(created)},
            message=f'{len(created)} product(s) created from PDF.',
            status_code=status.HTTP_201_CREATED,
        )
