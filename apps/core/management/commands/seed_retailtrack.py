"""
Seed demo data for RetailTrack: branches, categories, brands, suppliers, products,
and branch stock. Idempotent — safe to run multiple times.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import Branch, Warehouse
from apps.products.models import Category, Brand, Supplier, Product, BranchStock

from apps.companies.models import Company

class Command(BaseCommand):
    help = 'Seeds RetailTrack with demo branches, products, and stock data'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Seeding RetailTrack demo data...'))

        # Fetch the demo company created by seed_demo.py
        company = Company.objects.first()
        if not company:
            self.stdout.write(self.style.ERROR('No Company found! Please run `python seed_demo.py` first.'))
            return

        # ── Branches ──
        branches_data = [
            {'name': 'Main Store', 'code': 'MAIN', 'address': 'MG Road, Pune 411001', 'phone': '020-12345678', 'manager_name': 'Rahul Sharma', 'company': company},
            {'name': 'City Center', 'code': 'CC01', 'address': 'FC Road, Pune 411004', 'phone': '020-87654321', 'manager_name': 'Priya Deshmukh', 'company': company},
            {'name': 'Warehouse Hub', 'code': 'WH01', 'address': 'MIDC Hinjawadi, Pune', 'phone': '020-55551234', 'manager_name': 'Amit Kulkarni', 'company': company},
        ]
        branches = {}
        for bd in branches_data:
            b, created = Branch.objects.get_or_create(code=bd['code'], defaults=bd)
            branches[bd['code']] = b
            self.stdout.write(f"  {'✓ Created' if created else '  Exists'} branch: {b.name}")

        # ── Warehouses ──
        wh, created = Warehouse.objects.get_or_create(
            code='WH-MAIN', defaults={'name': 'Main Warehouse', 'branch': branches['WH01'], 'company': company}
        )
        self.stdout.write(f"  {'✓ Created' if created else '  Exists'} warehouse: {wh.name}")

        # ── Categories ──
        categories_data = [
            'Groceries', 'Beverages', 'Snacks', 'Dairy', 'Personal Care',
            'Cleaning', 'Stationery', 'Electronics', 'Confectionery',
        ]
        categories = {}
        for name in categories_data:
            c, created = Category.objects.get_or_create(name=name, company=company)
            categories[name] = c
            self.stdout.write(f"  {'✓ Created' if created else '  Exists'} category: {name}")

        # ── Brands ──
        brands_data = ['Amul', 'Parle', 'Hindustan Unilever', 'ITC', 'Dabur',
                        'Tata', 'Britannia', 'Nestle', 'P&G', 'Godrej']
        brands = {}
        for name in brands_data:
            b, created = Brand.objects.get_or_create(name=name, company=company)
            brands[name] = b
            self.stdout.write(f"  {'✓ Created' if created else '  Exists'} brand: {name}")

        # ── Suppliers ──
        suppliers_data = [
            {'name': 'Metro Cash & Carry', 'contact_person': 'Rajesh', 'phone': '9876543210', 'email': 'metro@example.com', 'gstin': '27AABCU9603R1ZM', 'company': company},
            {'name': 'Reliance Distribution', 'contact_person': 'Sanjay', 'phone': '9123456789', 'email': 'reliance@example.com', 'gstin': '27AABCR1234P1ZN', 'company': company},
            {'name': 'DMart Wholesale', 'contact_person': 'Anil', 'phone': '9988776655', 'email': 'dmart@example.com', 'gstin': '27AABCD5678Q1ZO', 'company': company},
        ]
        suppliers = {}
        for sd in suppliers_data:
            s, created = Supplier.objects.get_or_create(name=sd['name'], defaults=sd)
            suppliers[sd['name']] = s
            self.stdout.write(f"  {'✓ Created' if created else '  Exists'} supplier: {sd['name']}")

        # ── Products ──
        products_data = [
            {'name': 'Amul Gold Milk 500ml', 'sku': 'AMG-500', 'category': 'Dairy', 'brand': 'Amul', 'supplier': 'Metro Cash & Carry',
             'cost_price': 28, 'selling_price': 32, 'tax_percentage': 0, 'hsn_code': '0401', 'minimum_stock_level': 50, 'unit': 'Nos'},
            {'name': 'Parle-G Biscuits 250g', 'sku': 'PG-250', 'category': 'Snacks', 'brand': 'Parle', 'supplier': 'Reliance Distribution',
             'cost_price': 18, 'selling_price': 22, 'tax_percentage': 5, 'hsn_code': '1905', 'minimum_stock_level': 100, 'unit': 'Nos'},
            {'name': 'Tata Tea Gold 500g', 'sku': 'TTG-500', 'category': 'Beverages', 'brand': 'Tata', 'supplier': 'Metro Cash & Carry',
             'cost_price': 190, 'selling_price': 230, 'tax_percentage': 5, 'hsn_code': '0902', 'minimum_stock_level': 30, 'unit': 'Nos'},
            {'name': 'Surf Excel Liquid 1L', 'sku': 'SEL-1L', 'category': 'Cleaning', 'brand': 'Hindustan Unilever', 'supplier': 'Reliance Distribution',
             'cost_price': 195, 'selling_price': 249, 'tax_percentage': 18, 'hsn_code': '3402', 'minimum_stock_level': 20, 'unit': 'Nos'},
            {'name': 'Maggi Noodles 70g', 'sku': 'MAG-70', 'category': 'Snacks', 'brand': 'Nestle', 'supplier': 'DMart Wholesale',
             'cost_price': 12, 'selling_price': 14, 'tax_percentage': 5, 'hsn_code': '1902', 'minimum_stock_level': 200, 'unit': 'Nos'},
            {'name': 'Amul Butter 500g', 'sku': 'AMB-500', 'category': 'Dairy', 'brand': 'Amul', 'supplier': 'Metro Cash & Carry',
             'cost_price': 250, 'selling_price': 290, 'tax_percentage': 12, 'hsn_code': '0405', 'minimum_stock_level': 25, 'unit': 'Nos'},
            {'name': 'Britannia Good Day 250g', 'sku': 'BGD-250', 'category': 'Snacks', 'brand': 'Britannia', 'supplier': 'Reliance Distribution',
             'cost_price': 35, 'selling_price': 45, 'tax_percentage': 5, 'hsn_code': '1905', 'minimum_stock_level': 80, 'unit': 'Nos'},
            {'name': 'Godrej No.1 Soap 100g', 'sku': 'GN1-100', 'category': 'Personal Care', 'brand': 'Godrej', 'supplier': 'DMart Wholesale',
             'cost_price': 25, 'selling_price': 35, 'tax_percentage': 18, 'hsn_code': '3401', 'minimum_stock_level': 40, 'unit': 'Nos'},
            {'name': 'Dabur Honey 500g', 'sku': 'DH-500', 'category': 'Groceries', 'brand': 'Dabur', 'supplier': 'Metro Cash & Carry',
             'cost_price': 210, 'selling_price': 270, 'tax_percentage': 0, 'hsn_code': '0409', 'minimum_stock_level': 15, 'unit': 'Nos'},
            {'name': 'ITC Classmate Notebook A4', 'sku': 'ICN-A4', 'category': 'Stationery', 'brand': 'ITC', 'supplier': 'Reliance Distribution',
             'cost_price': 30, 'selling_price': 40, 'tax_percentage': 12, 'hsn_code': '4820', 'minimum_stock_level': 50, 'unit': 'Nos'},
            {'name': 'Nestle Everyday Dairy Whitener 1kg', 'sku': 'NED-1K', 'category': 'Dairy', 'brand': 'Nestle', 'supplier': 'DMart Wholesale',
             'cost_price': 340, 'selling_price': 410, 'tax_percentage': 5, 'hsn_code': '0402', 'minimum_stock_level': 20, 'unit': 'Nos'},
            {'name': 'P&G Gillette Guard Razor', 'sku': 'PGR-01', 'category': 'Personal Care', 'brand': 'P&G', 'supplier': 'Reliance Distribution',
             'cost_price': 35, 'selling_price': 50, 'tax_percentage': 18, 'hsn_code': '8212', 'minimum_stock_level': 30, 'unit': 'Nos'},
        ]

        product_objs = []
        for pd in products_data:
            p, created = Product.objects.get_or_create(
                sku=pd['sku'],
                company=company,
                defaults={
                    'name': pd['name'],
                    'category': categories[pd['category']],
                    'brand': brands[pd['brand']],
                    'supplier': suppliers[pd['supplier']],
                    'cost_price': pd['cost_price'],
                    'selling_price': pd['selling_price'],
                    'tax_percentage': pd['tax_percentage'],
                    'hsn_code': pd['hsn_code'],
                    'minimum_stock_level': pd['minimum_stock_level'],
                    'unit': pd['unit'],
                }
            )
            product_objs.append(p)
            self.stdout.write(f"  {'✓ Created' if created else '  Exists'} product: {p.name} [{p.barcode}]")

        # ── Seed stock in branches ──
        import random
        main_branch = branches['MAIN']
        cc_branch = branches['CC01']

        for p in product_objs:
            stock_main = random.randint(5, 150)
            stock_cc = random.randint(0, 80)

            bs1, created = BranchStock.objects.get_or_create(
                product=p, branch=main_branch, warehouse=None, company=company,
                defaults={'quantity': stock_main}
            )
            if not created:
                bs1.quantity = stock_main
                bs1.save()

            bs2, created = BranchStock.objects.get_or_create(
                product=p, branch=cc_branch, warehouse=None, company=company,
                defaults={'quantity': stock_cc}
            )
            if not created:
                bs2.quantity = stock_cc
                bs2.save()

        self.stdout.write(f"  ✓ Stocked {len(product_objs)} products in 2 branches")

        self.stdout.write(self.style.SUCCESS(f'\n✅ Seeded: {len(branches)} branches, {len(categories)} categories, '
                                              f'{len(brands)} brands, {len(suppliers)} suppliers, '
                                              f'{len(product_objs)} products'))
