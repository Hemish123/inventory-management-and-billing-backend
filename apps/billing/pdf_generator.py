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

# ────────────────────────────────────────────────────────────────
# Essae PR-55 Thermal Printer — 80mm roll, ~72mm printable area
# Paper width:     79.5 ± 0.5 mm
# Printable width: ~72 mm
# Safe content:    ~68 mm (with small inner margins)
# ────────────────────────────────────────────────────────────────

# Paper & margin constants (in mm)
PAPER_WIDTH_MM = 72          # printable area of 80mm roll
MARGIN_LR_MM = 2             # left/right margins
MARGIN_TB_MM = 3             # top/bottom margins
CONTENT_WIDTH_MM = PAPER_WIDTH_MM - (2 * MARGIN_LR_MM)  # 68mm usable

# Separator that fits 68mm at 7pt Courier
SEPARATOR = "─" * 32


def generate_bill_pdf(bill):
    """Generate Thermal Receipt PDF optimised for Essae PR-55 (80mm roll)."""

    # Dynamic page height based on item count
    base_height = 145 * mm
    item_height = len(bill.items.all()) * 12 * mm
    page_height = base_height + item_height

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=(PAPER_WIDTH_MM * mm, page_height),
        leftMargin=MARGIN_LR_MM * mm,
        rightMargin=MARGIN_LR_MM * mm,
        topMargin=MARGIN_TB_MM * mm,
        bottomMargin=MARGIN_TB_MM * mm,
    )

    styles = getSampleStyleSheet()
    content_w = CONTENT_WIDTH_MM * mm  # usable width in points

    # ── Paragraph styles (small fonts for thermal receipt) ──────
    company_name = bill.company.name if bill.company else getattr(settings, 'COMPANY_NAME', 'Retail Store')
    name_len = len(company_name or '')
    shop_font_size = 7 if name_len > 25 else (7.5 if name_len > 15 else 8)
    shop_leading = shop_font_size + 2

    shop_name_style = ParagraphStyle(
        'ShopName',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=shop_font_size,
        leading=shop_leading,
        alignment=1,  # Center
        spaceAfter=1,
        wordWrap='CJK',  # Force character-level wrapping for long names
    )

    center_bold = ParagraphStyle(
        'CenterBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        alignment=1,
        spaceAfter=1,
    )

    center_normal = ParagraphStyle(
        'CenterNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
        alignment=1,
        spaceAfter=1,
    )

    normal = ParagraphStyle(
        'ThermalNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
        spaceAfter=1,
    )

    normal_right = ParagraphStyle(
        'ThermalRight',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
        spaceAfter=1,
        alignment=2,  # Right
    )

    # ── Build elements ──────────────────────────────────────────
    elements = []

    # 1. Header — Logo + Company Info
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
                logo_width = 30 * mm  # smaller logo for 72mm
                logo_height = logo_width * aspect_ratio

                if logo_height > 20 * mm:
                    logo_height = 20 * mm
                    logo_width = logo_height / aspect_ratio

                im = Image(logo_path, width=logo_width, height=logo_height)
                im.hAlign = 'CENTER'
                elements.append(im)
                elements.append(Spacer(1, 1.5 * mm))
            except Exception:
                pass

    elements.append(Paragraph(company_name, shop_name_style))

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

    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(SEPARATOR, center_normal))
    elements.append(Paragraph("TAX INVOICE / CASH MEMO", center_bold))
    elements.append(Paragraph(SEPARATOR, center_normal))

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

    elements.append(Spacer(1, 1.5 * mm))
    elements.append(Paragraph(SEPARATOR, center_normal))

    # 3. Items Table
    # Column widths tuned for 68mm content area:
    #   Item name: 32mm | Qty×Price: 18mm | Total: 18mm  = 68mm
    col_item = 32 * mm
    col_qty  = 18 * mm
    col_tot  = 18 * mm

    item_header_style = ParagraphStyle(
        'ItemHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
    )
    item_header_right = ParagraphStyle(
        'ItemHeaderRight',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        alignment=2,
    )
    item_val_style = ParagraphStyle(
        'ItemVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
        wordWrap='CJK',
    )
    item_val_right = ParagraphStyle(
        'ItemValRight',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
        alignment=2,
    )

    item_data = [[
        Paragraph('Item', item_header_style),
        Paragraph('Qty x Price', item_header_right),
        Paragraph('Total', item_header_right),
    ]]

    disc_line_style = ParagraphStyle(
        'DiscLine', parent=styles['Normal'],
        fontName='Helvetica-Oblique', fontSize=6, leading=8, textColor=colors.gray,
    )

    for item in bill.items.all():
        name_para = Paragraph(str(item.product_name), item_val_style)
        qty_price = Paragraph(f"{item.quantity} x {item.unit_price}", item_val_right)
        total = Paragraph(f"{item.line_total:.2f}", item_val_right)
        item_data.append([name_para, qty_price, total])
        # Line-item discount row
        item_disc = float(getattr(item, 'discount_amount', 0) or 0)
        if item_disc > 0:
            disc_type = getattr(item, 'discount_type', 'FIXED')
            disc_pct = float(getattr(item, 'discount_percentage', 0) or 0)
            if disc_type == 'PERCENTAGE' and disc_pct > 0:
                disc_text = f"Disc ({disc_pct:.0f}%): -{item_disc:.2f}"
            else:
                disc_text = f"Disc: -{item_disc:.2f}"
            item_data.append([Paragraph(disc_text, disc_line_style), '', ''])

    item_table = Table(item_data, colWidths=[col_item, col_qty, col_tot])
    item_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(item_table)
    elements.append(Spacer(1, 1.5 * mm))
    elements.append(Paragraph(SEPARATOR, center_normal))

    # 4. Totals
    # Two columns: label (right-aligned) + value (right-aligned)
    #   Label: 46mm | Value: 22mm = 68mm
    col_label = 46 * mm
    col_value = 22 * mm

    totals_data = []
    totals_data.append([
        Paragraph('Subtotal:', normal_right),
        Paragraph(f"{bill.subtotal:.2f}", normal_right),
    ])
    totals_data.append([
        Paragraph('Tax (GST):', normal_right),
        Paragraph(f"{bill.tax_total:.2f}", normal_right),
    ])

    # Overall Discount
    bill_disc_amt = float(getattr(bill, 'discount_amount', 0) or 0)
    bill_disc_type = getattr(bill, 'discount_type', 'NONE')
    bill_disc_pct = float(getattr(bill, 'discount_percentage', 0) or 0)
    if bill_disc_amt > 0:
        if bill_disc_type == 'PERCENTAGE' and bill_disc_pct > 0:
            disc_label = f'Discount ({bill_disc_pct:.0f}%):'
        else:
            disc_label = 'Discount:'
        totals_data.append([
            Paragraph(disc_label, normal_right),
            Paragraph(f"-{bill_disc_amt:.2f}", normal_right),
        ])

    # Round off
    bill_round_off = float(getattr(bill, 'round_off', 0) or 0)
    if bill_round_off != 0:
        totals_data.append([
            Paragraph('Round Off:', normal_right),
            Paragraph(f"{bill_round_off:+.2f}", normal_right),
        ])

    # Grand Total (bold, slightly larger)
    gt_style = ParagraphStyle(
        'GrandTotal',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=2,
    )
    totals_data.append([
        Paragraph('GRAND TOTAL:', gt_style),
        Paragraph(f"{bill.grand_total:.2f}", gt_style),
    ])

    t_table = Table(totals_data, colWidths=[col_label, col_value])
    t_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('LINEABOVE', (0, -1), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(t_table)

    # 5. Payment Details
    if hasattr(bill, 'payments') and bill.payments.exists():
        elements.append(Spacer(1, 1.5 * mm))
        elements.append(Paragraph(SEPARATOR, center_normal))
        elements.append(Paragraph("PAYMENT DETAILS", center_bold))
        pay_data = []
        for p in bill.payments.all():
            pay_data.append([
                Paragraph(p.payment_method, normal),
                Paragraph(f"{p.amount:.2f}", normal_right),
            ])
        p_table = Table(pay_data, colWidths=[col_label, col_value])
        p_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(p_table)
    else:
        # Backward compatibility — single payment method
        elements.append(Spacer(1, 1.5 * mm))
        elements.append(Paragraph(SEPARATOR, center_normal))
        elements.append(Paragraph(f"Paid by: {bill.payment_method}", center_bold))

    # 6. You Saved section
    # Calculate total savings (overall discount + all item-level discounts)
    total_saved = bill_disc_amt
    for item in bill.items.all():
        total_saved += float(getattr(item, 'discount_amount', 0) or 0)
    if total_saved > 0:
        elements.append(Spacer(1, 1.5 * mm))
        saved_style = ParagraphStyle(
            'YouSaved', parent=styles['Normal'],
            fontName='Helvetica-Bold', fontSize=8, leading=10,
            alignment=1, textColor=colors.HexColor('#006600'),
        )
        elements.append(Paragraph(f"*** You Saved: ₹{total_saved:.2f} ***", saved_style))

    # 7. Footer
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(SEPARATOR, center_normal))
    elements.append(Spacer(1, 1.5 * mm))

    no_exchange_style = ParagraphStyle(
        'NoExchange',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        alignment=1,
        spaceAfter=2,
        textColor=colors.black,
    )
    elements.append(Paragraph("*** NO EXCHANGE / NO RETURN ***", no_exchange_style))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph("Thank you for shopping with us!", center_bold))
    elements.append(Paragraph("Please visit again.", center_normal))
    elements.append(Spacer(1, 1.5 * mm))
    brand_style = ParagraphStyle(
        'DevBrand',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=6.5,
        leading=8,
        alignment=1,
        textColor=colors.HexColor('#555555'),
    )
    elements.append(Paragraph("Made with ❤️ by JMS TechNova", brand_style))

    doc.build(elements)
    return buf.getvalue()
