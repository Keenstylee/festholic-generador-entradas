from __future__ import annotations

from io import BytesIO
import re

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


TICKET_FIELDS = {
    # x, top, width, height, font size, text color
    "schedule": (145, 52, 105, 42, 9, "#ffffff"),
    "location": (145, 94, 105, 24, 9, "#ffffff"),
    "ticket_type": (19, 228, 245, 19, 10, "#8055e8"),
    "row": (269, 228, 29, 19, 10, "#8055e8"),
    "seat": (299, 228, 39, 19, 10, "#8055e8"),
    "category": (65, 255, 120, 19, 10, "#8055e8"),
    "event": (64, 335, 135, 18, 8, "#999999"),
}

# Coordenadas de origen de los textos editables en el PDF (x, y desde abajo).
# Se eliminan los operadores de texto en estas áreas, sin pintar el fondo.
EDITABLE_TEXT_ORIGINS = (
    (140, 510, 255, 570),  # día, fecha, hora y ubicación
    (15, 378, 265, 390),   # sector / tipo de entrada
    (270, 378, 300, 390),  # fila
    (300, 378, 335, 390),  # asiento
    (60, 350, 190, 365),   # categoría
    (60, 272, 205, 285),   # evento
)

# Área de la ilustración del artista en la cabecera. No invade la fecha ni el QR.
EVENT_IMAGE_AREA = (0, 33, 136, 101)
# Margen interior para que el logo no ocupe por completo la cabecera.
EVENT_IMAGE_PADDING = 12
QR_IMAGE_AREA = (263, 49, 70, 70)


def inspect_pdf(data: bytes) -> dict:
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("El PDF está protegido con contraseña.")
    return {
        "pages": len(reader.pages),
        "metadata": reader.metadata,
    }


def inspect_ticket_fields(data: bytes) -> dict[str, str]:
    """Extrae los datos visibles de una entrada Teleticket compatible."""
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("El PDF está protegido con contraseña.")
    if not reader.pages:
        raise ValueError("El PDF no contiene páginas.")
    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    text = page.extract_text() or ""
    if not (330 <= width <= 350 and 615 <= height <= 635 and "Sector" in text and "Asiento" in text):
        raise ValueError(
            "Este editor visual está preparado para entradas Teleticket con el formato del ejemplo. "
            "El PDF cargado tiene otra plantilla."
        )

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    def after(label: str) -> str:
        for index, line in enumerate(lines[:-1]):
            if line.casefold() == label.casefold():
                return lines[index + 1]
        return ""

    schedule_index = next(
        (index for index, line in enumerate(lines) if re.match(
            r"^(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes|S[aá]bado|Domingo),", line, re.IGNORECASE
        )),
        -1,
    )
    schedule = re.match(r"^([^,]+),\s*(.+)$", lines[schedule_index]) if schedule_index >= 0 else None
    sector_index = next((i for i, line in enumerate(lines) if line.casefold() == "sector"), -1)
    flat_text = " ".join(lines)

    def value_after_label(label: str) -> str:
        match = re.search(rf"\b{label}\s+([^\s]+)", flat_text, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    ticket_type = lines[sector_index + 1] if sector_index >= 0 and sector_index + 1 < len(lines) else ""
    if not ticket_type:
        ticket_match = re.search(r"\bSector\s+(.+?)\s+Fila\b", flat_text, re.IGNORECASE)
        ticket_type = ticket_match.group(1).strip() if ticket_match else ""

    category = ""
    for line in lines:
        if not re.match(r"^Categor", line, re.IGNORECASE) or ":" not in line:
            continue
        candidate = line.split(":", 1)[1].strip()
        candidate = re.sub(r"\s+Sector\s*$", "", candidate, flags=re.IGNORECASE).strip()
        if candidate:
            category = candidate
            break
    if not category and sector_index >= 0:
        fila_index = next(
            (i for i in range(sector_index + 2, len(lines)) if lines[i].casefold() == "fila"),
            -1,
        )
        if fila_index > sector_index:
            candidates = [
                line for line in lines[sector_index + 2:fila_index]
                if not re.match(r"^(?:S/\s*)?[\d.,]+$", line, re.IGNORECASE)
            ]
            if candidates:
                category = candidates[-1]

    return {
        "day": schedule.group(1).title() if schedule else "",
        "date": schedule.group(2).strip() if schedule else "",
        "time": lines[schedule_index + 1] if schedule_index >= 0 and schedule_index + 1 < len(lines) else "",
        "location": lines[schedule_index + 2] if schedule_index >= 0 and schedule_index + 2 < len(lines) else "",
        "event": lines[schedule_index + 3] if schedule_index >= 0 and schedule_index + 3 < len(lines) else "",
        "ticket_type": ticket_type,
        "row": after("Fila") or value_after_label("Fila"),
        "seat": after("Asiento") or value_after_label("Asiento"),
        "category": category,
    }


def _hex_color(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _draw_replacement(overlay, page_height: float, spec, lines: list[str]) -> None:
    x, top, width, height, font_size, foreground = spec
    bottom = page_height - top - height
    overlay.setFillColorRGB(*_hex_color(foreground))
    overlay.setFont("Helvetica", font_size)
    if len(lines) == 1:
        overlay.drawString(x + 1, bottom + max(3, (height - font_size) / 2), lines[0])
    else:
        baseline = page_height - top - font_size - 1
        for line in lines:
            overlay.drawString(x + 1, baseline, line)
            baseline -= font_size + 3


def _remove_editable_text(page, reader: PdfReader) -> None:
    """Quita solo los textos editables y conserva intacto el arte de fondo."""
    contents = page.get_contents()
    if contents is None:
        return
    stream = ContentStream(contents, reader)
    current_x = current_y = None
    filtered = []
    for operands, operator in stream.operations:
        if operator == b"BT":
            current_x = current_y = 0.0
        elif operator == b"Tm" and len(operands) >= 6:
            current_x = float(operands[4])
            current_y = float(operands[5])
        elif operator in (b"Td", b"TD") and len(operands) >= 2:
            current_x = (current_x or 0.0) + float(operands[0])
            current_y = (current_y or 0.0) + float(operands[1])
        is_text = operator in (b"Tj", b"TJ", b"'", b'"')
        editable = (
            is_text
            and current_x is not None
            and current_y is not None
            and any(x0 <= current_x <= x1 and y0 <= current_y <= y1
                    for x0, y0, x1, y1 in EDITABLE_TEXT_ORIGINS)
        )
        if not editable:
            filtered.append((operands, operator))
    stream.operations = filtered
    page.replace_contents(stream)


def _qr_xobject_names(page) -> set[str]:
    """Localiza imágenes cuadradas grandes; en esta plantilla corresponde al QR."""
    names: set[str] = set()
    resources = page.get("/Resources", {})
    for name, reference in resources.get("/XObject", {}).items():
        obj = reference.get_object()
        if obj.get("/Subtype") != "/Image":
            continue
        width = int(obj.get("/Width", 0))
        height = int(obj.get("/Height", 0))
        if min(width, height) >= 200 and 0.9 <= width / max(height, 1) <= 1.1:
            names.add(str(name))
    return names


def _remove_original_qr_image(page, reader: PdfReader) -> None:
    names = _qr_xobject_names(page)
    if not names or page.get_contents() is None:
        raise ValueError("No se pudo localizar el QR original dentro del PDF.")
    stream = ContentStream(page.get_contents(), reader)
    stream.operations = [
        (operands, operator)
        for operands, operator in stream.operations
        if not (operator == b"Do" and operands and str(operands[0]) in names)
    ]
    page.replace_contents(stream)


def extract_embedded_qr_payload(data: bytes) -> str:
    """Lee el QR raster incrustado para comprobar que el reemplazo sea equivalente."""
    import cv2
    import numpy as np

    reader = PdfReader(BytesIO(data))
    detector = cv2.QRCodeDetector()
    for page in reader.pages:
        for embedded in page.images:
            image = np.asarray(embedded.image.convert("RGB"))[:, :, ::-1]
            decoded, _, _ = detector.detectAndDecode(image)
            if decoded:
                return decoded
    return ""


def _draw_event_image(
    overlay,
    page_height: float,
    image_data: bytes,
    mode: str = "contain",
) -> None:
    """Reemplaza la ilustración superior conservando relación de aspecto."""
    x, top, width, height = EVENT_IMAGE_AREA
    bottom = page_height - top - height
    overlay.setFillColorRGB(*_hex_color("#4215a3"))
    overlay.rect(x, bottom, width, height, fill=1, stroke=0)

    padding = EVENT_IMAGE_PADDING
    content_x = x + padding
    content_bottom = bottom + padding
    content_width = width - (padding * 2)
    content_height = height - (padding * 2)

    with Image.open(BytesIO(image_data)) as source:
        source = source.convert("RGBA")
        target_size = (
            max(1, round(content_width * 4)),
            max(1, round(content_height * 4)),
        )
        if mode == "cover":
            prepared = ImageOps.fit(source, target_size, method=Image.Resampling.LANCZOS)
        else:
            prepared = ImageOps.contain(source, target_size, method=Image.Resampling.LANCZOS)

        png = BytesIO()
        prepared.save(png, format="PNG")
        png.seek(0)
        draw_width = prepared.width / 4
        draw_height = prepared.height / 4
        draw_x = content_x + (content_width - draw_width) / 2
        draw_y = content_bottom + (content_height - draw_height) / 2
        overlay.drawImage(
            ImageReader(png), draw_x, draw_y,
            width=draw_width, height=draw_height,
            preserveAspectRatio=True, mask="auto",
        )


def _draw_reconstructed_qr(overlay, page_height: float, qr_data: bytes) -> None:
    x, top, width, height = QR_IMAGE_AREA
    bottom = page_height - top - height
    try:
        with Image.open(BytesIO(qr_data)) as source:
            qr = source.convert("L")
            # Fuerza blanco y negro puro y mantiene bordes de módulo nítidos.
            qr = qr.point(lambda value: 255 if value >= 128 else 0, mode="1")
            png = BytesIO()
            qr.save(png, format="PNG")
            png.seek(0)
            overlay.drawImage(
                ImageReader(png), x, bottom,
                width=width, height=height,
                preserveAspectRatio=True,
            )
    except (OSError, ValueError) as exc:
        raise ValueError("El QR reconstruido no es una imagen válida.") from exc


def edit_ticket_fields(
    data: bytes,
    fields: dict[str, str],
    event_image: bytes | None = None,
    image_mode: str = "contain",
    reconstructed_qr: bytes | None = None,
) -> bytes:
    """Reemplaza campos visibles de la entrada sin tocar el QR ni sus códigos."""
    inspect_ticket_fields(data)
    reader = PdfReader(BytesIO(data))
    writer = PdfWriter()
    first = reader.pages[0]
    width = float(first.mediabox.width)
    height = float(first.mediabox.height)
    _remove_editable_text(first, reader)
    if reconstructed_qr:
        _remove_original_qr_image(first, reader)

    overlay_buffer = BytesIO()
    overlay = canvas.Canvas(overlay_buffer, pagesize=(width, height))
    if event_image:
        try:
            _draw_event_image(overlay, height, event_image, image_mode)
        except (OSError, ValueError) as exc:
            raise ValueError("La imagen del evento no es válida.") from exc
    if reconstructed_qr:
        _draw_reconstructed_qr(overlay, height, reconstructed_qr)
    schedule = [
        f"{fields.get('day', '').strip()}, {fields.get('date', '').strip()}",
        fields.get("time", "").strip(),
    ]
    _draw_replacement(overlay, height, TICKET_FIELDS["schedule"], schedule)
    for name in ("location", "ticket_type", "row", "seat", "category", "event"):
        _draw_replacement(
            overlay,
            height,
            TICKET_FIELDS[name],
            [fields.get(name, "").strip()],
        )
    overlay.save()
    overlay_buffer.seek(0)
    overlay_page = PdfReader(overlay_buffer).pages[0]
    first.merge_page(overlay_page)
    writer.add_page(first)
    for page in reader.pages[1:]:
        writer.add_page(page)
    if reader.metadata:
        writer.add_metadata({str(k): str(v) for k, v in reader.metadata.items() if v is not None})
    output = BytesIO()
    writer.write(output)
    result = output.getvalue()
    if len(PdfReader(BytesIO(result)).pages) != len(reader.pages):
        raise RuntimeError("El PDF editado no superó la validación.")
    return result


def parse_page_order(value: str, total: int) -> list[int]:
    """Convierte '3, 1, 2' en índices base cero y valida duplicados/rango."""
    try:
        order = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise ValueError("El orden debe contener números separados por comas.") from exc
    if not order:
        raise ValueError("Debes conservar al menos una página.")
    if len(order) != len(set(order)):
        raise ValueError("El orden no puede repetir páginas.")
    if any(page < 1 or page > total for page in order):
        raise ValueError(f"Las páginas deben estar entre 1 y {total}.")
    return [page - 1 for page in order]


def edit_pdf(data: bytes, order: list[int], rotations: dict[int, int]) -> bytes:
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("El PDF está protegido con contraseña.")
    writer = PdfWriter()
    for source_index in order:
        page = reader.pages[source_index]
        rotation = rotations.get(source_index, 0) % 360
        if rotation:
            page.rotate(rotation)
        writer.add_page(page)
    if reader.metadata:
        metadata = {str(k): str(v) for k, v in reader.metadata.items() if v is not None}
        writer.add_metadata(metadata)
    output = BytesIO()
    writer.write(output)
    result = output.getvalue()
    validation = PdfReader(BytesIO(result))
    if len(validation.pages) != len(order):
        raise RuntimeError("El PDF editado no superó la validación de páginas.")
    return result
