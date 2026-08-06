import os
from io import BytesIO
import hashlib
from django.conf import settings

# Monkeypatch hashlib.md5 to fix ReportLab 4.x compatibility on Python 3.8
# which doesn't support the usedforsecurity argument
_orig_md5 = hashlib.md5
def _patched_md5(*args, **kwargs):
    kwargs.pop('usedforsecurity', None)
    return _orig_md5(*args, **kwargs)
hashlib.md5 = _patched_md5

from reportlab.lib.pagesizes import portrait
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode import qr

def generate_bill_pdf(bill):
    """Generate Thermal Receipt (80mm) PDF for a given Bill instance."""
    
    # 80mm width is approx 226 points (80 * 72 / 25.4)
    # Height will be dynamic based on items
    base_height = 150 * mm
    item_height = len(bill.items.all()) * 15 * mm
    
    page_width = 80 * mm
    page_height = base_height + item_height
    
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=(page_width, page_height),
        leftMargin=3*mm,
        rightMargin=3*mm,
        topMargin=5*mm,
        bottomMargin=5*mm,
    )
    
    styles = getSampleStyleSheet()
    
    # Define thermal styles
    center_bold = ParagraphStyle(
        'CenterBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        alignment=1, # Center
        spaceAfter=2
    )
    center_normal = ParagraphStyle(
        'CenterNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        alignment=1, # Center
        spaceAfter=1
    )
    normal = ParagraphStyle(
        'ThermalNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        spaceAfter=1
    )
    
    elements = []
    
    # 1. Header (Company Info)
    company_name = bill.company.name if bill.company else getattr(settings, 'COMPANY_NAME', 'Retail Store')
    
    # Try to load and add the logo if it exists
    if bill.company and getattr(bill.company, 'logo', None) and getattr(bill.company.logo, 'url', None):
        logo_path = bill.company.logo.path
        if os.path.exists(logo_path):
            try:
                from PIL import Image as PILImage
                with PILImage.open(logo_path) as img:
                    img_width, img_height = img.size
                
                aspect_ratio = img_height / float(img_width)
                logo_width = 40 * mm
                logo_height = logo_width * aspect_ratio
                
                if logo_height > 30 * mm:
                    logo_height = 30 * mm
                    logo_width = logo_height / aspect_ratio
                    
                im = Image(logo_path, width=logo_width, height=logo_height)
                im.hAlign = 'CENTER'
                elements.append(im)
                elements.append(Spacer(1, 2*mm))
            except Exception:
                pass

    elements.append(Paragraph(company_name, center_bold))
    
    if bill.company:
        address_parts = [part for part in [bill.company.address, bill.company.city, bill.company.state] if part]
        company_address = ", ".join(address_parts)
        company_phone = bill.company.phone
        company_gst = bill.company.gst_number
    else:
        company_address = getattr(settings, 'COMPANY_ADDRESS', '')
        company_phone = getattr(settings, 'COMPANY_PHONE', '')
        company_gst = getattr(settings, 'COMPANY_GST', '')

    if company_address:
        elements.append(Paragraph(company_address, center_normal))
    if company_phone:
        elements.append(Paragraph(f"Ph: {company_phone}", center_normal))
    if company_gst:
        elements.append(Paragraph(f"GSTIN: {company_gst}", center_normal))
        
    elements.append(Spacer(1, 3*mm))
    elements.append(Paragraph("-" * 42, center_normal))
    elements.append(Paragraph("TAX INVOICE / CASH MEMO", center_bold))
    elements.append(Paragraph("-" * 42, center_normal))
    
    # 2. Bill Info
    elements.append(Paragraph(f"<b>Bill No:</b> {bill.bill_number}", normal))
    elements.append(Paragraph(f"<b>Date:</b> {bill.billing_date.strftime('%d-%m-%Y %H:%M')}", normal))
    if bill.branch:
        elements.append(Paragraph(f"<b>Branch:</b> {bill.branch.name}", normal))
    if bill.cashier:
        elements.append(Paragraph(f"<b>Cashier:</b> {bill.cashier.first_name or bill.cashier.email}", normal))
    elements.append(Paragraph(f"<b>Customer:</b> {bill.customer_name}", normal))
    if bill.customer_phone:
        elements.append(Paragraph(f"<b>Phone:</b> {bill.customer_phone}", normal))
        
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph("-" * 42, center_normal))
    
    # 3. Items Table
    item_data = [['Item', 'Qty x Price', 'Total']]
    
    for item in bill.items.all():
        name_para = Paragraph(item.product_name, normal)
        qty_price = Paragraph(f"{item.quantity} x {item.unit_price}", normal)
        total = Paragraph(f"{item.line_total:.2f}", normal)
        item_data.append([name_para, qty_price, total])
        # If there's line item discount, show it below
        if getattr(item, 'discount_amount', 0) > 0:
             item_data.append([Paragraph(f"<font size=7 color=gray>Disc: -{item.discount_amount}</font>", normal), '', ''])

    item_table = Table(item_data, colWidths=[38*mm, 20*mm, 16*mm])
    item_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LINEBELOW', (0,0), (-1,0), 0.5, colors.black),
        ('BOTTOMPADDING', (0,0), (-1,0), 2),
        ('TOPPADDING', (0,0), (-1,-1), 1),
        ('BOTTOMPADDING', (0,1), (-1,-1), 1),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph("-" * 42, center_normal))
    
    # 4. Totals
    totals_data = []
    totals_data.append(['Subtotal:', f"{bill.subtotal:.2f}"])
    totals_data.append(['Tax (GST):', f"{bill.tax_total:.2f}"])
    
    # Overall Discount
    if getattr(bill, 'discount_amount', 0) > 0:
        totals_data.append([f"Discount:", f"-{bill.discount_amount:.2f}"])
        
    # Round off
    if getattr(bill, 'round_off', 0) != 0:
        totals_data.append(['Round Off:', f"{bill.round_off:+.2f}"])
        
    totals_data.append(['GRAND TOTAL:', f"{bill.grand_total:.2f}"])
    
    t_table = Table(totals_data, colWidths=[54*mm, 20*mm])
    t_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-2), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('ALIGN', (0,0), (0,-1), 'RIGHT'),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,-1), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 1),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
    ]))
    elements.append(t_table)
    
    # 5. Payments
    if hasattr(bill, 'payments') and bill.payments.exists():
        elements.append(Spacer(1, 2*mm))
        elements.append(Paragraph("-" * 42, center_normal))
        elements.append(Paragraph("PAYMENT DETAILS", center_bold))
        pay_data = []
        for p in bill.payments.all():
            pay_data.append([p.payment_method, f"{p.amount:.2f}"])
        p_table = Table(pay_data, colWidths=[54*mm, 20*mm])
        p_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('TOPPADDING', (0,0), (-1,-1), 1),
            ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ]))
        elements.append(p_table)
    else:
        # Backward compatibility if no split payments recorded
        elements.append(Spacer(1, 2*mm))
        elements.append(Paragraph("-" * 42, center_normal))
        elements.append(Paragraph(f"Paid by: {bill.payment_method}", center_bold))
        
    # 7. Footer
    elements.append(Spacer(1, 5*mm))
    elements.append(Paragraph("Thank you for shopping with us!", center_bold))
    elements.append(Paragraph("Please visit again.", center_normal))
    
    doc.build(elements)
    return buf.getvalue()
