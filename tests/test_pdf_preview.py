from io import BytesIO

from PIL import Image
from pypdf import PdfWriter

from src.pdf_preview import pdf_page_count, render_pdf_page


def sample_pdf(pages: int = 2) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=340, height=624)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_preview_renders_selected_page_as_png():
    source = sample_pdf()
    assert pdf_page_count(source) == 2
    image_data = render_pdf_page(source, 1, 1.25)
    with Image.open(BytesIO(image_data)) as image:
        assert image.format == "PNG"
        assert image.width == 425
        assert image.height == 780


def test_pdf_preview_rejects_invalid_page():
    try:
        render_pdf_page(sample_pdf(1), 2)
    except ValueError as error:
        assert "no existe" in str(error)
    else:
        raise AssertionError("Se esperaba ValueError para una página inexistente")
