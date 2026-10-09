from __future__ import annotations

from io import BytesIO
from datetime import datetime
import json
import re

import pymupdf
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


TELETICKET_FIELDS = {
    # x, top, width, height, font size, text color
    "schedule": (145, 52, 105, 42, 9, "#ffffff"),
    "location": (145, 94, 105, 24, 9, "#ffffff"),
    "ticket_type": (19, 228, 245, 19, 10, "#8055e8"),
    "row": (269, 228, 29, 19, 10, "#8055e8"),
    "seat": (299, 228, 39, 19, 10, "#8055e8"),
    "category": (65, 255, 120, 19, 10, "#8055e8"),
    "event": (64, 335, 135, 18, 8, "#999999"),
    "producer": (64, 358, 130, 18, 8, "#999999"),
    "ruc": (64, 382, 125, 18, 8, "#999999"),
    "price": (273, 380, 62, 18, 8, "#999999"),
    "qr_number": (256, 35, 84, 18, 8.5, "#000000"),
    "qr_code": (256, 116.5, 84, 18, 8.5, "#000000"),
}

TICKETMASTER_FIELDS = {
    # Coordenadas físicas A4: x, distancia superior, ancho, alto, tamaño y color.
    "schedule": (29, 224, 150, 34, 8.5, "#ffffff"),
    "location": (29, 165, 150, 48, 8.5, "#ffffff"),
    "ticket_type": (208, 132, 272, 19, 9.5, "#111111"),
    "row": (0, 0, 0, 0, 1, "#111111"),
    "seat": (0, 0, 0, 0, 1, "#111111"),
    "category": (208, 183, 145, 19, 8.5, "#111111"),
    "event": (208, 101, 265, 22, 9.5, "#111111"),
    "event_left": (29, 139, 150, 22, 9, "#ffffff"),
    "producer": (107, 760, 430, 18, 7.5, "#ffffff"),
    "ruc": (0, 0, 0, 0, 1, "#111111"),
    "price": (208, 216, 110, 20, 8.5, "#111111"),
    "qr_number": (119, 273, 70, 19, 8.5, "#ffffff"),
    "purchase_number": (27, 273, 70, 19, 8.5, "#ffffff"),
    "qr_code": (480, 181, 96, 18, 8, "#111111"),
    "detail": (208, 153, 275, 22, 8.5, "#111111"),
}

# Coordenadas de origen de los textos editables en el PDF (x, y desde abajo).
# Se eliminan los operadores de texto en estas áreas, sin pintar el fondo.
TELETICKET_EDITABLE_TEXT_ORIGINS = (
    # Plantillas anteriores, con coordenadas de texto positivas.
    (140, 510, 255, 570),  # día, fecha, hora y ubicación
    (15, 378, 265, 390),   # sector / tipo de entrada
    (270, 378, 300, 390),  # fila
    (300, 378, 335, 390),  # asiento
    (60, 350, 190, 365),   # categoría
    (60, 272, 205, 285),   # evento
    (60, 245, 195, 265),   # productor
    (265, 220, 338, 245),  # precio
    (60, 220, 190, 245),   # RUC
    # Plantilla Teleticket nueva. Su contenido usa una transformación que deja
    # los orígenes de texto en coordenadas Y negativas dentro del stream.
    (140, -100, 255, -40),   # día, fecha, hora y ubicación
    (15, -230, 265, -215),   # sector / tipo de entrada
    (265, -230, 340, -215),  # fila y asiento
    (60, -255, 190, -245),   # categoría
    (60, -333, 220, -320),   # evento
    (60, -356, 200, -345),   # productor
    (265, -380, 338, -365),  # precio
    (60, -382, 190, -365),   # RUC
)

TELETICKET_EDITABLE_IDENTIFIER_ORIGINS = (
    (275, -53, 340, -42),     # número superior del QR
    (255, -127, 340, -114),   # código inferior del QR
    # Variantes con coordenadas positivas de las plantillas anteriores.
    (275, 570, 340, 586),
    (255, 487, 340, 505),
)

TICKETMASTER_EDITABLE_TEXT_ORIGINS = (
    (20, 160, 190, 310),     # evento, lugar y fecha en la columna azul
    (250, 115, 720, 295),    # evento, sector, detalle, categoría, precios y código
    (120, 995, 760, 1020),   # productor, RUC y dirección del pie
)
TICKETMASTER_EDITABLE_IDENTIFIER_ORIGINS = (
    (140, 330, 230, 365),    # número de ticket
    (620, 225, 760, 255),    # código inferior del QR
)

TEMPLATE_PROFILES = {
    "teleticket": {
        "fields": TELETICKET_FIELDS,
        "editable": TELETICKET_EDITABLE_TEXT_ORIGINS,
        "identifiers": TELETICKET_EDITABLE_IDENTIFIER_ORIGINS,
        "event_images": ((0, 33, 136, 101, 12, "#4215a3"),),
        "qr_area": (266.5, 52, 62, 62),
        "qr_clear": (256, 52, 84, 68),
        "number_prefix": "N° ",
        "clear_rects": (),
        "identifier_clear_rects": (),
    },
    "ticketmaster": {
        "fields": TICKETMASTER_FIELDS,
        "editable": TICKETMASTER_EDITABLE_TEXT_ORIGINS,
        "identifiers": TICKETMASTER_EDITABLE_IDENTIFIER_ORIGINS,
        "event_images": (
            (8, 14, 578, 49, 4, "#000000"),
            (298, 307, 278, 204, 0, "#000000"),
        ),
        "qr_area": (493, 99, 70, 70),
        "qr_clear": (482, 93, 92, 110),
        "number_prefix": "",
        "clear_rects": (
            (20, 134, 165, 28, "#1179e9"),
            (20, 162, 165, 45, "#1179e9"),
            (20, 227, 165, 34, "#1179e9"),
            (204, 98, 275, 37, "#ffffff"),
            (204, 125, 280, 55, "#ffffff"),
            (204, 182, 150, 23, "#ffffff"),
            (204, 214, 120, 30, "#ffffff"),
            (100, 757, 460, 23, "#026cdf"),
        ),
        "identifier_clear_rects": (
            (20, 272, 77, 22, "#1179e9"),
            (106, 272, 79, 22, "#1179e9"),
        ),
    },
}


def inspect_pdf(data: bytes) -> dict:
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("El PDF está protegido con contraseña.")
    return {
        "pages": len(reader.pages),
        "metadata": reader.metadata,
    }


def detect_ticket_template(data: bytes) -> str:
    """Identifica el perfil visual sin depender del nombre del archivo."""
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("El PDF está protegido con contraseña.")
    if not reader.pages:
        raise ValueError("El PDF no contiene páginas.")
    metadata_template = str((reader.metadata or {}).get("/FestholicTemplate", "")).casefold()
    if metadata_template in TEMPLATE_PROFILES:
        return metadata_template
    page = reader.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    text = page.extract_text() or ""
    normalized = text.casefold()
    if 330 <= width <= 350 and 615 <= height <= 635 and "sector" in normalized and "asiento" in normalized:
        return "teleticket"
    if (
        585 <= width <= 605
        and 830 <= height <= 850
        and "ticketmaster" in normalized
        and "seccion:" in normalized
        and "ticket" in normalized
    ):
        return "ticketmaster"
    raise ValueError(
        "El PDF no coincide con las plantillas compatibles de Teleticket o Ticketmaster."
    )


def _inspect_ticketmaster_fields(lines: list[str], text: str) -> dict[str, str]:
    flat_text = " ".join(lines)
    detail = re.search(
        r"Secci[oó]n:\s*(.*?)\s*-\s*Fila:\s*(.*?)\s*-\s*Asiento:\s*([^\s]+)",
        flat_text,
        re.IGNORECASE,
    )
    schedule = re.search(r"(\d{2}/\d{2}/\d{4})\s+([^\s]+)", flat_text)
    producer_match = re.search(
        r"([^\n]+?)\s*-\s*Ruc\s*:\s*(\d{11})",
        text,
        re.IGNORECASE,
    )
    price_match = re.search(r"S/\.\s*[\d.,]+", flat_text, re.IGNORECASE)
    date_value = schedule.group(1) if schedule else ""
    day = ""
    if date_value:
        weekdays = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
        try:
            day = weekdays[datetime.strptime(date_value, "%d/%m/%Y").weekday()]
        except ValueError:
            pass

    date_index = next((i for i, line in enumerate(lines) if date_value and date_value in line), -1)
    venue_parts: list[str] = []
    for line in lines[1:date_index if date_index >= 0 else 1]:
        if line.upper() == line and re.search(r"[A-ZÁÉÍÓÚÑ]", line):
            venue_parts.append(line)
        else:
            break

    category = ""
    if detail:
        detail_index = next((i for i, line in enumerate(lines) if "Seccion:" in line or "Sección:" in line), -1)
        for line in lines[detail_index + 1:] if detail_index >= 0 else []:
            if re.fullmatch(r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s-]*", line) and line not in {"COMPRA", "TICKET"}:
                category = line
                break

    return {
        "day": day,
        "date": date_value,
        "time": schedule.group(2) if schedule else "",
        "location": " ".join(venue_parts),
        "event": lines[0] if lines else "",
        "producer": producer_match.group(1).strip() if producer_match else "",
        "price": price_match.group(0) if price_match else "",
        "ruc": producer_match.group(2) if producer_match else "",
        "ticket_type": detail.group(1).strip() if detail else "",
        "row": detail.group(2).strip() if detail else "",
        "seat": detail.group(3).strip() if detail else "",
        "category": category,
    }


def inspect_ticket_fields(data: bytes) -> dict[str, str]:
    """Extrae los datos visibles de una entrada Teleticket o Ticketmaster."""
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("El PDF está protegido con contraseña.")
    if not reader.pages:
        raise ValueError("El PDF no contiene páginas.")
    serialized_fields = (reader.metadata or {}).get("/FestholicFields")
    if serialized_fields:
        try:
            stored_fields = json.loads(str(serialized_fields))
            expected = {
                "day", "date", "time", "location", "event", "producer", "price",
                "ruc", "ticket_type", "row", "seat", "category",
            }
            if expected.issubset(stored_fields):
                return {name: str(stored_fields[name]) for name in expected}
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    template = detect_ticket_template(data)
    page = reader.pages[0]
    text = page.extract_text() or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if template == "ticketmaster":
        return _inspect_ticketmaster_fields(lines, text)

    def labeled_value(label: str) -> str:
        prefix = f"{label}:"
        for index, line in enumerate(lines):
            if not line.casefold().startswith(prefix.casefold()):
                continue
            inline = line[len(prefix):].strip()
            if inline:
                return inline
            if index + 1 < len(lines):
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
    extended_template = any(line.casefold() == "produce:" for line in lines)
    detail_match = re.search(
        r"\bSector\s+(.+?)\s+Fila\s+([^\s]+)\s+Asiento\s+([^\s]+)",
        flat_text,
        re.IGNORECASE,
    )
    ticket_type = lines[sector_index + 1] if sector_index >= 0 and sector_index + 1 < len(lines) else ""
    if detail_match:
        ticket_type = detail_match.group(1).strip()

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

    location_parts: list[str] = []
    event = labeled_value("Evento")
    producer = labeled_value("Produce")
    price = labeled_value("Precio")
    ruc = labeled_value("RUC")
    row = detail_match.group(2).strip() if detail_match else ""
    seat = detail_match.group(3).strip() if detail_match else ""

    # En la plantilla Teleticket nueva, pypdf devuelve primero las etiquetas
    # y al final los valores visuales en este orden estable.
    if extended_template and schedule_index >= 0:
        tail = lines[schedule_index + 2:]
        generated_identifiers = (
            len(tail) >= 8
            and re.match(r"^N(?:°|�)?\s*\d+$", tail[-2], re.IGNORECASE)
            and re.fullmatch(r"\d{10,}", re.sub(r"\s+", "", tail[-1]))
        )
        if generated_identifiers:
            # Las plantillas guardadas por este editor añaden los identificadores
            # al final del stream. Antes de ellos se mantienen, en orden, la
            # ubicación y los seis campos editables principales.
            editable_tail = tail[:-2]
            if len(editable_tail) >= 6:
                location_parts = editable_tail[:-6]
                ticket_type, category, event, producer, ruc, price = editable_tail[-6:]
        elif len(tail) >= 7:
            location_parts = tail[:-7]
            ticket_type, category, _order, event, price, producer, ruc = tail[-7:]
    elif schedule_index >= 0:
        for line in lines[schedule_index + 2:schedule_index + 5]:
            compact = re.sub(r"\s+", "", line)
            if (
                re.fullmatch(r"\d{10,}", compact)
                or re.search(r"\bSector\b", line, re.IGNORECASE)
                or re.match(r"^(Evento|Produce|RUC|Precio)\s*:", line, re.IGNORECASE)
            ):
                break
            location_parts.append(line)

    fallback_event_index = schedule_index + 2 + len(location_parts)
    fallback_event = (
        lines[fallback_event_index]
        if 0 <= fallback_event_index < len(lines)
        else ""
    )

    day = schedule.group(1).title() if schedule else ""
    if re.fullmatch(r"S.bado", day, re.IGNORECASE):
        day = "Sábado"
    elif re.fullmatch(r"Mi.rcoles", day, re.IGNORECASE):
        day = "Miércoles"

    return {
        "day": day,
        "date": schedule.group(2).strip() if schedule else "",
        "time": lines[schedule_index + 1] if schedule_index >= 0 and schedule_index + 1 < len(lines) else "",
        "location": " ".join(location_parts),
        "event": event or fallback_event,
        "producer": producer,
        "price": price,
        "ruc": ruc,
        "ticket_type": ticket_type,
        "row": row,
        "seat": seat,
        "category": category,
    }


def _hex_color(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _draw_replacement(overlay, page_height: float, spec, lines: list[str]) -> None:
    x, top, width, height, font_size, foreground = spec
    bottom = page_height - top - height
    overlay.setFillColorRGB(*_hex_color(foreground))

    def fitted_size(text: str) -> float:
        measured = pdfmetrics.stringWidth(text, "Helvetica", font_size)
        available = max(1.0, width - 2)
        if measured <= available:
            return float(font_size)
        return max(5.5, font_size * available / measured)

    if len(lines) == 1:
        size = fitted_size(lines[0])
        overlay.setFont("Helvetica", size)
        overlay.drawString(x + 1, bottom + max(3, (height - size) / 2), lines[0])
    else:
        baseline = page_height - top - font_size - 1
        for line in lines:
            overlay.setFont("Helvetica", fitted_size(line))
            overlay.drawString(x + 1, baseline, line)
            baseline -= font_size + 3


def _align_to_header(data: bytes, label: str, spec: tuple) -> tuple:
    """Centra una columna bajo su encabezado ('Fila' / 'Asiento') leído del PDF.

    Si el encabezado no se localiza cerca de la columna esperada, devuelve la
    especificación original sin cambios.
    """
    x, top, width, height, font_size, foreground = spec
    expected_center = x + width / 2
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            matches = document.load_page(0).search_for(label)
    except (RuntimeError, ValueError):
        return spec
    candidates = [
        rect for rect in matches
        if abs((rect.x0 + rect.x1) / 2 - expected_center) <= 30
        and -10 <= top - rect.y1 <= 70
    ]
    if not candidates:
        return spec
    header = min(candidates, key=lambda rect: abs((rect.x0 + rect.x1) / 2 - expected_center))
    center = (header.x0 + header.x1) / 2
    return (center - width / 2, top, width, height, font_size, foreground)


def _draw_centered_replacement(overlay, page_height: float, spec, text: str) -> None:
    """Dibuja los identificadores centrados con respecto a la matriz QR."""
    x, top, width, height, font_size, foreground = spec
    bottom = page_height - top - height
    available = max(1.0, width - 2)
    measured = pdfmetrics.stringWidth(text, "Helvetica", font_size)
    size = float(font_size) if measured <= available else max(5.5, font_size * available / measured)
    overlay.setFillColorRGB(*_hex_color(foreground))
    overlay.setFont("Helvetica", size)
    overlay.drawCentredString(x + width / 2, bottom + max(3, (height - size) / 2), text)


def _wrap_location(value: str, max_chars: int = 22) -> list[str]:
    """Divide ubicaciones largas en un máximo de dos líneas legibles."""
    words = value.split()
    if len(value) <= max_chars or len(words) < 2:
        return [value]
    first: list[str] = []
    while words and len(" ".join(first + [words[0]])) <= max_chars:
        first.append(words.pop(0))
    if not first:
        first.append(words.pop(0))
    return [" ".join(first), " ".join(words)] if words else [" ".join(first)]


def _remove_editable_text(
    page,
    reader: PdfReader,
    profile: dict,
    include_identifiers: bool = False,
) -> None:
    """Quita solo los textos editables y conserva intacto el arte de fondo."""
    contents = page.get_contents()
    if contents is None:
        return
    stream = ContentStream(contents, reader)
    current_x = current_y = None
    filtered = []
    editable_origins = profile["editable"] + (profile["identifiers"] if include_identifiers else ())
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
                    for x0, y0, x1, y1 in editable_origins)
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
        # Algunas entradas Teleticket incluyen el QR como trazos vectoriales.
        # Su área se limpia en la capa de reemplazo, sin tocar los números.
        return
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
    profile: dict,
    mode: str = "contain",
) -> None:
    """Reemplaza las ilustraciones configuradas conservando relación de aspecto."""
    with Image.open(BytesIO(image_data)) as source:
        source = source.convert("RGBA")
        for x, top, width, height, padding, background in profile["event_images"]:
            bottom = page_height - top - height
            overlay.setFillColorRGB(*_hex_color(background))
            overlay.rect(x, bottom, width, height, fill=1, stroke=0)
            content_x = x + padding
            content_bottom = bottom + padding
            content_width = width - (padding * 2)
            content_height = height - (padding * 2)
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


def _draw_reconstructed_qr(overlay, page_height: float, qr_data: bytes, profile: dict) -> None:
    x, top, width, height = profile["qr_area"]
    bottom = page_height - top - height
    clear_x, clear_top, clear_width, clear_height = profile["qr_clear"]
    overlay.setFillColorRGB(1, 1, 1)
    overlay.rect(clear_x, page_height - clear_top - clear_height, clear_width, clear_height, fill=1, stroke=0)
    try:
        with Image.open(BytesIO(qr_data)) as source:
            qr = source.convert("L")
            # Fuerza blanco y negro puro y mantiene bordes de módulo nítidos.
            qr = qr.point(lambda value: 255 if value >= 128 else 0, mode="1")
            # Centra la matriz negra, no los márgenes desiguales del PNG.
            ink_bounds = qr.convert("L").point(lambda value: 255 - value).getbbox()
            if ink_bounds is None:
                raise ValueError("El QR reconstruido está vacío.")
            qr = qr.crop(ink_bounds)
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


def _draw_profile_clear_rects(
    overlay,
    page_height: float,
    profile: dict,
    include_identifiers: bool,
) -> None:
    """Limpia zonas planas en plantillas cuyo texto no puede retirarse del stream."""
    rects = profile.get("clear_rects", ())
    if include_identifiers:
        rects += profile.get("identifier_clear_rects", ())
    for x, top, width, height, color in rects:
        overlay.setFillColorRGB(*_hex_color(color))
        overlay.rect(x, page_height - top - height, width, height, fill=1, stroke=0)


def edit_ticket_fields(
    data: bytes,
    fields: dict[str, str],
    event_image: bytes | None = None,
    image_mode: str = "contain",
    reconstructed_qr: bytes | None = None,
) -> bytes:
    """Reemplaza los campos visibles, los identificadores y el QR de la entrada."""
    inspect_ticket_fields(data)
    template = detect_ticket_template(data)
    profile = TEMPLATE_PROFILES[template]
    ticket_fields = profile["fields"]
    reader = PdfReader(BytesIO(data))
    writer = PdfWriter()
    first = reader.pages[0]
    width = float(first.mediabox.width)
    height = float(first.mediabox.height)
    replace_identifiers = bool(fields.get("qr_number", "").strip() and fields.get("qr_code", "").strip())
    _remove_editable_text(first, reader, profile, include_identifiers=replace_identifiers)
    if reconstructed_qr:
        _remove_original_qr_image(first, reader)

    overlay_buffer = BytesIO()
    overlay = canvas.Canvas(overlay_buffer, pagesize=(width, height))
    _draw_profile_clear_rects(overlay, height, profile, replace_identifiers)
    if event_image:
        try:
            _draw_event_image(overlay, height, event_image, profile, image_mode)
        except (OSError, ValueError) as exc:
            raise ValueError("La imagen del evento no es válida.") from exc
    if reconstructed_qr:
        _draw_reconstructed_qr(overlay, height, reconstructed_qr, profile)
    schedule = [
        f"{fields.get('day', '').strip()}, {fields.get('date', '').strip()}",
        fields.get("time", "").strip(),
    ]
    _draw_replacement(overlay, height, ticket_fields["schedule"], schedule)
    names = (
        ("location", "ticket_type", "category", "event", "price")
        if template == "ticketmaster"
        else ("location", "ticket_type", "row", "seat", "category", "event", "producer", "ruc", "price")
    )
    for name in names:
        value = fields.get(name, "").strip()
        if template == "teleticket" and name in {"row", "seat"}:
            header = "Fila" if name == "row" else "Asiento"
            _draw_centered_replacement(
                overlay, height, _align_to_header(data, header, ticket_fields[name]), value
            )
        else:
            _draw_replacement(
                overlay,
                height,
                ticket_fields[name],
                _wrap_location(value) if name == "location" else [value],
            )
    if template == "ticketmaster":
        _draw_replacement(
            overlay,
            height,
            ticket_fields["event_left"],
            [fields.get("event", "").strip()],
        )
        detail = (
            f"Sección: {fields.get('ticket_type', '').strip()} - "
            f"Fila: {fields.get('row', '').strip()} - Asiento: {fields.get('seat', '').strip()}"
        )
        _draw_replacement(overlay, height, ticket_fields["detail"], [detail])
        producer_line = f"{fields.get('producer', '').strip()} - RUC: {fields.get('ruc', '').strip()}"
        _draw_replacement(overlay, height, ticket_fields["producer"], [producer_line])
    if replace_identifiers:
        if template == "ticketmaster":
            _draw_centered_replacement(
                overlay,
                height,
                ticket_fields["purchase_number"],
                fields.get("qr_number", "").strip(),
            )
        _draw_centered_replacement(
            overlay,
            height,
            ticket_fields["qr_number"],
            f"{profile['number_prefix']}{fields.get('qr_number', '').strip()}",
        )
        _draw_centered_replacement(
            overlay,
            height,
            ticket_fields["qr_code"],
            fields.get("qr_code", "").strip(),
        )
    overlay.save()
    overlay_buffer.seek(0)
    overlay_page = PdfReader(overlay_buffer).pages[0]
    first.merge_page(overlay_page)
    writer.add_page(first)
    for page in reader.pages[1:]:
        writer.add_page(page)
    metadata = {str(k): str(v) for k, v in (reader.metadata or {}).items() if v is not None}
    metadata["/FestholicTemplate"] = template
    metadata["/FestholicFields"] = json.dumps(
        {
            name: fields.get(name, "")
            for name in (
                "day", "date", "time", "location", "event", "producer", "price",
                "ruc", "ticket_type", "row", "seat", "category",
            )
        },
        ensure_ascii=False,
    )
    writer.add_metadata(metadata)
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