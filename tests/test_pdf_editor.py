from io import BytesIO

from pypdf import PdfReader, PdfWriter

from reportlab.pdfgen import canvas

from src.pdf_editor import edit_pdf, edit_ticket_fields, inspect_ticket_fields, parse_page_order


def sample_pdf(pages=3):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=300)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_parse_order():
    assert parse_page_order("3, 1", 3) == [2, 0]


def test_edit_reorders_deletes_and_rotates():
    result = edit_pdf(sample_pdf(), [2, 0], {2: 90, 0: 90})
    reader = PdfReader(BytesIO(result))
    assert len(reader.pages) == 2
    assert reader.pages[0].rotation == 90


def sample_ticket_pdf():
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(340.157, 623.622))
    for line, y in [
        ("Lunes, 31 De Agosto", 560), ("2026 / 21:00 Hrs", 548),
        ("Estadio Nacional", 520), ("Sector PLATINUM LATERAL Fila 78 Asiento 19", 390),
        ("Categoría: PRE-VENTA IBK Sector", 365),
        ("Evento: MAROON 5 EN LIMA CONCERTS", 280),
    ]:
        pdf.drawString(20, y, line)
    pdf.save()
    return output.getvalue()


def test_ticket_fields_are_detected_and_replaced():
    source = sample_ticket_pdf()
    detected = inspect_ticket_fields(source)
    assert detected["row"] == "78"
    assert detected["seat"] == "19"
    assert detected["ticket_type"] == "PLATINUM LATERAL"
    assert detected["category"] == "PRE-VENTA IBK"
    result = edit_ticket_fields(source, {**detected, "row": "12", "seat": "34"})
    assert len(PdfReader(BytesIO(result)).pages) == 1


def test_ticket_event_image_can_be_replaced():
    from PIL import Image

    image_data = BytesIO()
    Image.new("RGBA", (400, 200), (255, 255, 255, 255)).save(image_data, format="PNG")
    source = sample_ticket_pdf()
    detected = inspect_ticket_fields(source)
    result = edit_ticket_fields(source, detected, event_image=image_data.getvalue())
    assert len(PdfReader(BytesIO(result)).pages) == 1
