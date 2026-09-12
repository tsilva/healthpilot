"""Render a reviewed food-plan JSON spec; no nutrition inference or API access."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle
from pypdf import PdfReader


def draw_swaps(c, spec, page_w, page_h, para):
    """Draw the optional, explicitly requested exchange sheet on one page."""
    y = page_h - 40

    def text(value, gap=8):
        nonlocal y
        p = para(value)
        _, height = p.wrap(515, page_h)
        if y - height < 40:
            raise ValueError('Swaps do not fit one page at readable size')
        p.drawOn(c, 40, y - height)
        y -= height + gap

    text(spec['title'])
    if spec.get('intro'):
        text(spec['intro'])
    sections = spec.get('sections')
    if not isinstance(sections, list) or not sections:
        raise ValueError('Swaps require nonempty sections')
    for section in sections:
        text(section['title'])
        columns, rows = section['columns'], section['rows']
        widths = section['widths']
        if (not columns or not rows or len(widths) != len(columns)
                or any(type(w) not in (int, float) or w <= 16 for w in widths)
                or abs(sum(widths) - 515) > .01
                or any(len(row) != len(columns) for row in rows)):
            raise ValueError('Invalid swap table columns, rows or widths')
        cells = [[para(v, index == 0) for v in row]
                 for index, row in enumerate([columns] + rows)]
        table = Table(cells, colWidths=widths)
        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), .4, colors.HexColor('#B2C4BE')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E5EFEB')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        _, height = table.wrap(515, page_h)
        if y - height < 40:
            raise ValueError('Swaps do not fit one page at readable size')
        table.drawOn(c, 40, y - height)
        y -= height + 12
    for note in spec.get('notes', []):
        text(note)


def render(spec, output):
    style = ParagraphStyle('cell', fontName='Helvetica', fontSize=9, leading=11)
    widths = [193, 242, 80]
    rows, heights, bands = [], [], []

    def plain(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Labels and quantities must be nonempty text')
        if any(ord(c) > 255 and c not in '–—≈’“”' for c in value):
            raise ValueError('Text needs a Unicode font; adapt renderer before using this language')
        return value

    def para(value, bold=False):
        value = escape(plain(value))
        return Paragraph(f'<b>{value}</b>' if bold else value, style)

    def add(values, minimum=28, bold=False):
        cells = [para(v, bold) for v in values]
        height = max(minimum, max(p.wrap(w - 16, 1000)[1]
                                    for p, w in zip(cells, widths)) + 10)
        rows.append(cells)
        heights.append(height)

    columns = spec.get('columns', ['Food', 'Quantity / weight state', 'kcal ≈'])
    if not isinstance(columns, list) or len(columns) != 3:
        raise ValueError('columns must have three labels')
    add(columns, bold=True)
    meals = spec.get('meals')
    if not isinstance(meals, list) or not meals:
        raise ValueError('At least one meal is required')
    total = 0
    for meal in meals:
        items = meal.get('items')
        if not isinstance(items, list) or not items:
            raise ValueError('Every meal requires items')
        subtotal = 0
        for item in items:
            kcal = item.get('kcal')
            if type(kcal) is not int or kcal < 0:
                raise ValueError('Meal calories must be nonnegative integers; use unquantified for unknowns')
            subtotal += kcal
        band = len(rows)
        add([meal['name'], '-', str(subtotal)], minimum=25, bold=True)
        bands.append(band)
        for item in items:
            add([item['food'], item['quantity'], str(item['kcal'])])
        total += subtotal
    total_row = len(rows)
    # A small visible dash keeps the optional note structurally valid.
    unknown = spec.get('unquantified', [])
    if not isinstance(unknown, list):
        raise ValueError('unquantified must be a list')
    if unknown and not spec.get('total_note'):
        raise ValueError('Explain exclusion of unquantified items in total_note')
    add([spec.get('total_label', 'FOOD TOTAL'), spec.get('total_note') or '-',
         f'{total:,}'.replace(',', '.')], minimum=30, bold=True)
    for item in unknown:
        if 'kcal' not in item or item['kcal'] is not None:
            raise ValueError('Unquantified items must explicitly have null kcal')
        add([item['food'], item['quantity'], spec.get('unknown_label', 'Unknown')], minimum=32)

    page_w, page_h = A4
    bottom = page_h - 40 - sum(heights)
    if bottom < 40:
        raise ValueError('Menu does not fit one page at readable size; shorten wording without dropping items')
    note, footer = spec.get('note', ''), spec.get('footer', '')
    for text, size in [(note, 9), (footer, 7.5)]:
        if text:
            plain(text)
            if '\n' in text or stringWidth(text, 'Helvetica', size) > sum(widths):
                raise ValueError('Measurement note/footer must fit one line')
    commands = [('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), .4, colors.HexColor('#B2C4BE')),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8)]
    for i in [0] + bands + [total_row]:
        commands.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#E5EFEB')))
    for i in bands:
        commands.append(('SPAN', (0, i), (1, i)))
    table = Table(rows, colWidths=widths, rowHeights=heights)
    table.setStyle(TableStyle(commands))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(suffix='.pdf', dir=output.parent)
    os.close(fd)
    try:
        c = canvas.Canvas(temp, pagesize=A4)
        c.setTitle(spec.get('title', 'Food plan'))
        c.setFont('Helvetica', 9)
        c.drawString(40, page_h - 25, note)
        table.wrapOn(c, page_w, page_h)
        table.drawOn(c, 40, bottom)
        c.setFont('Helvetica', 7.5)
        c.drawString(40, bottom - 14, footer)
        swaps = spec.get('swaps')
        if swaps is not None:
            c.showPage()
            draw_swaps(c, swaps, page_w, page_h, para)
        c.save()
        reader = PdfReader(temp)
        expected_pages = 2 if swaps is not None else 1
        if len(reader.pages) != expected_pages:
            raise ValueError(f'Expected exactly {expected_pages} pages')
        os.replace(temp, output)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return total


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    total = render(json.loads(args.spec.read_text()), args.output)
    print(f'Validated {len(PdfReader(args.output).pages)} page(s); food total {total} kcal; {args.output.resolve()}')
