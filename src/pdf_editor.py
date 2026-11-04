from __future__ import annotations

from io import BytesIO
from datetime import datetime
import json
import re

import pymupdf
from PIL import Image, ImageDraw, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream
from reportlab.lib.colors import HexColor
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

TICKETMASTER_DEFAULTS = {
    "address": "Av. 28 de Julio, Lima s/n, Lima",
    "admission_type": "VIP",
    "door": "",
    "service_charge": "S/. 0.00",
    "total_price": "S/. 0.00",
    "producer_address": "Velasco Astete 1243 San Borja",
}

JOINNUS_DEFAULTS = {
    "address": "AV. ALFREDO MENDIOLA 3301",
    "attendee_name": "PROHIBIDA SU VENTA",
    "attendee_dni": "74711061",
    "transaction": "849B6AFD4FBA08FC441E",
    "purchase_date": "23/10/2026 - 07:25:09 AM",
    "purchase_number": "36132649",
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

JOINNUS_FIELDS = {}

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
            (8, 14, 578, 49, 0, "#000000", "cover"),
            (298, 307, 278, 204, 0, "#000000", "contain"),
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
    "joinnus": {
        "fields": JOINNUS_FIELDS,
        "editable": (),
        "identifiers": (),
        "event_images": ((49.2, 194.7, 46, 46, 0, "#ffffff", "cover", 7),),
        "qr_area": (68.7, 76.2, 84.5, 84.5),
        "qr_clear": (60.2, 68.2, 101.5, 101.5),
        "number_prefix": "",
        "clear_rects": (),
        "identifier_clear_rects": (),
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
    if (
        600 <= width <= 620
        and 780 <= height <= 805
        and "joinnus" in normalized
        and "nro. de compra" in normalized
        and "detalles de la compra" in normalized
    ):
        return "joinnus"
    raise ValueError(
        "El PDF no coincide con las plantillas compatibles de Teleticket, Ticketmaster o Joinnus."
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
        r"([^\n]+?)\s*-\s*Ruc\s*:\s*(\d{11})(?:\s*-\s*Dir\s*:\s*([^\n]+))?",
        text,
        re.IGNORECASE,
    )
    prices = re.findall(r"S/\.\s*[\d.,]+", flat_text, re.IGNORECASE)
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

    admission_type = ""
    detail_line_index = next(
        (i for i, line in enumerate(lines) if re.search(r"Secci[oó]n:", line, re.IGNORECASE)),
        -1,
    )
    if detail_line_index > 0:
        admission_type = lines[detail_line_index - 1]

    address_parts: list[str] = []
    if date_index > 0:
        venue_end = 1 + len(venue_parts)
        address_parts = lines[venue_end:date_index]

    return {
        "day": day,
        "date": date_value,
        "time": schedule.group(2) if schedule else "",
        "location": " ".join(venue_parts),
        "address": " ".join(address_parts),
        "event": lines[0] if lines else "",
        "producer": producer_match.group(1).strip() if producer_match else "",
        "producer_address": producer_match.group(3).strip() if producer_match and producer_match.group(3) else "",
        "price": prices[0] if prices else "",
        "service_charge": prices[1] if len(prices) > 1 else "",
        "total_price": prices[2] if len(prices) > 2 else "",
        "ruc": producer_match.group(2) if producer_match else "",
        "admission_type": admission_type,
        "ticket_type": detail.group(1).strip() if detail else "",
        "row": detail.group(2).strip() if detail else "",
        "seat": detail.group(3).strip() if detail else "",
        "category": category,
        "door": "",
    }


def _joinnus_text(value: str) -> str:
    """Corrige los caracteres que algunos PDF de Joinnus extraen como reemplazos."""
    return (
        str(value or "")
        .replace("Pe�a", "Peña")
        .replace("s�b.", "sáb.")
        .replace("S�b.", "Sáb.")
        .replace("CORTES�A", "CORTESÍA")
        .replace("Direcci�n", "Dirección")
        .strip()
    )


def _inspect_joinnus_fields(lines: list[str], text: str) -> dict[str, str]:
    clean = [_joinnus_text(line) for line in lines]

    def after(label: str) -> str:
        for index, line in enumerate(clean):
            if line.casefold() == label.casefold() and index + 1 < len(clean):
                return clean[index + 1]
        return ""

    purchase_match = re.search(r"Nro\.\s*de\s*compra:\s*([^\s]+)", " ".join(clean), re.IGNORECASE)
    schedule_line = clean[8] if len(clean) > 8 else ""
    schedule_match = re.match(
        r"(.+?)\s+(\d{1,2}:\d{2}\s*(?:AM|PM))\s+(.+)$",
        schedule_line,
        re.IGNORECASE,
    )
    date_part = schedule_match.group(1).strip() if schedule_match else ""
    day, _, date_value = date_part.partition(" ")
    producer_line = after("Organizado por:")
    producer_match = re.match(r"(.+?)\s*-\s*(\d{11})$", producer_line)

    return {
        "day": day.rstrip(".").title(),
        "date": date_value.strip(),
        "time": schedule_match.group(2).strip() if schedule_match else "",
        "location": schedule_match.group(3).strip() if schedule_match else "",
        "address": after("Dirección del evento:"),
        "event": clean[7] if len(clean) > 7 else "",
        "producer": producer_match.group(1).strip() if producer_match else producer_line,
        "ruc": producer_match.group(2) if producer_match else "",
        "price": after("Precio de la entrada"),
        "ticket_type": after("Tipo de entrada"),
        "row": "",
        "seat": "",
        "category": "",
        "attendee_name": after("Nombre"),
        "attendee_dni": after("DNI"),
        "transaction": after("Transacción"),
        "purchase_date": after("Fecha de compra"),
        "purchase_number": purchase_match.group(1) if purchase_match else "",
    }


def inspect_ticket_fields(data: bytes) -> dict[str, str]:
    """Extrae los datos visibles de una entrada compatible."""
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
                result = {name: str(stored_fields[name]) for name in expected}
                template = detect_ticket_template(data)
                if template == "ticketmaster":
                    result.update({
                        name: str(stored_fields.get(name, default))
                        for name, default in TICKETMASTER_DEFAULTS.items()
                    })
                elif template == "joinnus":
                    result.update({
                        name: str(stored_fields.get(name, default))
                        for name, default in JOINNUS_DEFAULTS.items()
                    })
                return result
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    template = detect_ticket_template(data)
    page = reader.pages[0]
    text = page.extract_text() or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if template == "ticketmaster":
        return _inspect_ticketmaster_fields(lines, text)
    if template == "joinnus":
        return _inspect_joinnus_fields(lines, text)

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
        for image_spec in profile["event_images"]:
            x, top, width, height, padding, background = image_spec[:6]
            area_mode = image_spec[6] if len(image_spec) > 6 else mode
            corner_radius = image_spec[7] if len(image_spec) > 7 else 0
            bottom = page_height - top - height
            overlay.setFillColorRGB(*_hex_color(background))
            if corner_radius:
                overlay.roundRect(x, bottom, width, height, corner_radius, fill=1, stroke=0)
            else:
                overlay.rect(x, bottom, width, height, fill=1, stroke=0)
            content_x = x + padding
            content_bottom = bottom + padding
            content_width = width - (padding * 2)
            content_height = height - (padding * 2)
            target_size = (
                max(1, round(content_width * 4)),
                max(1, round(content_height * 4)),
            )
            if area_mode == "cover":
                prepared = ImageOps.fit(source, target_size, method=Image.Resampling.LANCZOS)
            else:
                prepared = ImageOps.contain(source, target_size, method=Image.Resampling.LANCZOS)

            if corner_radius:
                mask = Image.new("L", prepared.size, 0)
                ImageDraw.Draw(mask).rounded_rectangle(
                    (0, 0, prepared.width - 1, prepared.height - 1),
                    radius=max(1, round(corner_radius * 4)),
                    fill=255,
                )
                prepared.putalpha(mask)

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
            if profile is TEMPLATE_PROFILES["ticketmaster"] and top == 14:
                # La marca permanece visible aunque la imagen cubra toda la franja.
                overlay.setFillColorRGB(0, 0, 0)
                overlay.roundRect(x + 37, bottom + 6, 38, 37, 4, fill=1, stroke=0)
                overlay.setFillColorRGB(1, 1, 1)
                overlay.setFont("Helvetica-BoldOblique", 24)
                overlay.drawString(x + 49, bottom + 13, "t")


def _draw_reconstructed_qr(overlay, page_height: float, qr_data: bytes, profile: dict) -> None:
    x, top, width, height = profile["qr_area"]
    bottom = page_height - top - height
    clear_x, clear_top, clear_width, clear_height = profile["qr_clear"]
    overlay.setFillColorRGB(1, 1, 1)
    if profile is TEMPLATE_PROFILES["joinnus"]:
        overlay.roundRect(
            clear_x,
            page_height - clear_top - clear_height,
            clear_width,
            clear_height,
            10,
            fill=1,
            stroke=0,
        )
    else:
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
            if profile is TEMPLATE_PROFILES["joinnus"]:
                center_x = x + width / 2
                center_y = bottom + height / 2
                overlay.setFillColorRGB(1, 1, 1)
                overlay.setStrokeColorRGB(*_hex_color("#9aa8b6"))
                overlay.setLineWidth(0.7)
                overlay.circle(center_x, center_y, 10.2, fill=1, stroke=1)
                overlay.setFillColorRGB(*_hex_color("#19dbc1"))
                overlay.circle(center_x, center_y, 8.4, fill=1, stroke=0)
                overlay.setStrokeColorRGB(*_hex_color("#07141c"))
                overlay.setLineWidth(2.1)
                overlay.setLineCap(1)
                mark = overlay.beginPath()
                mark.moveTo(center_x - 5.0, center_y + 2.2)
                mark.curveTo(center_x - 5.0, center_y - 2.6, center_x - 1.0, center_y - 3.5, center_x - 1.0, center_y + 1.4)
                mark.moveTo(center_x + 1.2, center_y + 2.2)
                mark.curveTo(center_x + 1.2, center_y - 2.8, center_x + 5.0, center_y - 3.3, center_x + 5.0, center_y + 2.2)
                overlay.drawPath(mark, fill=0, stroke=1)
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


def _draw_fitted_line(
    overlay,
    page_height: float,
    text: str,
    x: float,
    top: float,
    width: float,
    font_size: float,
    font_name: str = "Helvetica",
    color: str = "#111111",
) -> None:
    value = str(text or "").strip()
    size = float(font_size)
    while size > 5.5 and pdfmetrics.stringWidth(value, font_name, size) > width:
        size -= 0.25
    overlay.setFillColorRGB(*_hex_color(color))
    overlay.setFont(font_name, size)
    overlay.drawString(x, page_height - top - size, value)


def _draw_wrapped_lines(
    overlay,
    page_height: float,
    text: str,
    x: float,
    top: float,
    width: float,
    font_size: float,
    font_name: str,
    color: str,
    max_lines: int = 2,
) -> None:
    words = str(text or "").split()
    lines: list[str] = []
    while words and len(lines) < max_lines:
        line: list[str] = []
        while words:
            candidate = " ".join(line + [words[0]])
            if line and pdfmetrics.stringWidth(candidate, font_name, font_size) > width:
                break
            line.append(words.pop(0))
        lines.append(" ".join(line))
    if words and lines:
        lines[-1] = f"{lines[-1]} {' '.join(words)}"
    for index, line in enumerate(lines):
        _draw_fitted_line(
            overlay, page_height, line, x, top + index * (font_size + 2),
            width, font_size, font_name, color,
        )


def _draw_ticketmaster_layout(
    overlay,
    page_height: float,
    fields: dict[str, str],
    include_identifiers: bool,
) -> None:
    """Reconstruye las zonas variables conservando el diseño Ticketmaster."""
    blue = "#1179e9"
    dark_blue = "#026cdf"
    line_blue = "#d7eafb"
    white = "#ffffff"
    black = "#111111"
    muted = "#8d8d8d"

    # Columna azul: secciones, separadores y tipografía del documento original.
    left_x, left_width = 8, 181
    overlay.setFillColorRGB(*_hex_color(dark_blue))
    overlay.rect(left_x, page_height - 126, left_width, 49, fill=1, stroke=0)
    _draw_fitted_line(overlay, page_height, "ticketmaster", 27, 94, 145, 17, "Helvetica-BoldOblique", white)
    for top, height in ((126, 27), (153, 46), (199, 50), (249, 45)):
        overlay.setFillColorRGB(*_hex_color(blue))
        overlay.rect(left_x, page_height - top - height, left_width, height, fill=1, stroke=0)
        overlay.setFillColorRGB(*_hex_color(dark_blue))
        overlay.rect(left_x, page_height - top - 3, left_width, 3, fill=1, stroke=0)
    overlay.setFillColorRGB(*_hex_color(dark_blue))
    overlay.rect(103, page_height - 294, 4, 45, fill=1, stroke=0)

    _draw_fitted_line(overlay, page_height, fields.get("event", ""), 27, 136, 150, 9.5, "Helvetica-Bold", white)
    _draw_wrapped_lines(overlay, page_height, fields.get("location", ""), 27, 160, 150, 9.5, "Helvetica-Bold", white)
    _draw_wrapped_lines(overlay, page_height, fields.get("address", ""), 27, 205, 150, 8.5, "Helvetica", white)
    schedule = f"{fields.get('date', '').strip()} {fields.get('time', '').strip()}".strip()
    _draw_fitted_line(overlay, page_height, schedule, 27, 232, 150, 9.5, "Helvetica-Bold", white)
    _draw_fitted_line(overlay, page_height, "COMPRA", 27, 257, 70, 9.5, "Helvetica-Bold", white)
    _draw_fitted_line(overlay, page_height, "TICKET", 126, 257, 55, 9.5, "Helvetica-Bold", white)
    if include_identifiers:
        _draw_fitted_line(overlay, page_height, fields.get("purchase_number", ""), 27, 274, 70, 9, "Helvetica", white)
        _draw_fitted_line(overlay, page_height, fields.get("ticket_number", ""), 126, 274, 55, 9, "Helvetica", white)

    # Área blanca: cada grupo mantiene la línea azul y la jerarquía original.
    content_x, content_top, content_width, content_height = 189, 77, 397, 217
    overlay.setFillColorRGB(1, 1, 1)
    overlay.rect(content_x, page_height - content_top - content_height, content_width, content_height, fill=1, stroke=0)
    overlay.setStrokeColorRGB(*_hex_color(dark_blue))
    overlay.setLineWidth(1)
    overlay.rect(8, page_height - 294, 578, 217, fill=0, stroke=1)

    text_x, text_width = 208, 245
    for top in (125, 151, 177, 207):
        overlay.setStrokeColorRGB(*_hex_color(line_blue))
        overlay.setLineWidth(0.8)
        overlay.line(text_x, page_height - top, 453, page_height - top)

    _draw_fitted_line(overlay, page_height, fields.get("event", ""), text_x, 103, text_width, 10.5, "Helvetica-Bold", black)
    _draw_fitted_line(overlay, page_height, fields.get("admission_type", ""), text_x, 130, text_width, 10, "Helvetica", black)
    detail = (
        f"Seccion: {fields.get('ticket_type', '').strip()} - "
        f"Fila: {fields.get('row', '').strip()} - Asiento: {fields.get('seat', '').strip()}"
    )
    _draw_fitted_line(overlay, page_height, detail, text_x, 156, 270, 9.5, "Helvetica", black)
    _draw_fitted_line(overlay, page_height, "TARIFA", text_x, 182, 62, 7.5, "Helvetica-Bold", muted)
    _draw_fitted_line(overlay, page_height, "PUERTA", 285, 182, 62, 7.5, "Helvetica-Bold", muted)
    _draw_fitted_line(overlay, page_height, fields.get("category", ""), text_x, 194, 70, 9.5, "Helvetica", black)
    _draw_fitted_line(overlay, page_height, fields.get("door", ""), 285, 194, 62, 9.5, "Helvetica", black)

    price_columns = (
        (text_x, "PRECIO", fields.get("price", ""), 72),
        (273, "CARGO POR SERVICIO", fields.get("service_charge", ""), 92),
        (370, "PRECIO TOTAL", fields.get("total_price", ""), 82),
    )
    for x, label, value, width in price_columns:
        _draw_fitted_line(overlay, page_height, label, x, 216, width, 7.5, "Helvetica-Bold", muted)
        _draw_fitted_line(overlay, page_height, value, x, 230, width, 9.5, "Helvetica", black)

    # Pie del productor con la dirección completa y el peso del original.
    overlay.setFillColorRGB(*_hex_color(dark_blue))
    overlay.roundRect(8, page_height - 780, 578, 26, 3, fill=1, stroke=0)
    producer_line = (
        f"{fields.get('producer', '').strip()} - Ruc:{fields.get('ruc', '').strip()}"
        f"-Dir :{fields.get('producer_address', '').strip()}"
    )
    size = 9.5
    while size > 6 and pdfmetrics.stringWidth(producer_line, "Helvetica-Bold", size) > 540:
        size -= 0.25
    overlay.setFillColorRGB(1, 1, 1)
    overlay.setFont("Helvetica-Bold", size)
    overlay.drawCentredString(297, page_height - 771, producer_line)


def _draw_joinnus_layout(
    overlay,
    page_height: float,
    fields: dict[str, str],
) -> None:
    """Reconstruye todas las zonas variables de la entrada Joinnus."""
    ink = "#0d1b2a"
    muted = "#5f6670"
    green = "#00a884"
    mint = "#dffbf8"
    border = "#c9d9e7"
    white = "#ffffff"

    def rect_from_top(x: float, top: float, width: float, height: float, color: str) -> None:
        overlay.setFillColorRGB(*_hex_color(color))
        overlay.rect(x, page_height - top - height, width, height, fill=1, stroke=0)

    # Número de compra en una sola línea, sin el salto visual del reemplazo anterior.
    rect_from_top(440, 17, 138, 24, white)
    purchase_label = "Nro. de compra:"
    purchase_x = 454
    purchase_top = 24
    purchase_size = 7.8
    purchase_y = page_height - purchase_top - purchase_size
    overlay.setFillColorRGB(*_hex_color(ink))
    overlay.setFont("Helvetica", purchase_size)
    overlay.drawString(purchase_x, purchase_y, purchase_label)
    number_x = purchase_x + pdfmetrics.stringWidth(purchase_label, "Helvetica", purchase_size) + 4
    _draw_fitted_line(
        overlay, page_height, fields.get("purchase_number", ""),
        number_x, 23.2, 575 - number_x, 8.7, "Helvetica-Bold", ink,
    )

    # Tarjeta de acceso completa; el QR reconstruido se dibuja encima después.
    card_x = 49.2
    card_y = page_height - 178
    card_width = 513.6
    card_height = 122
    overlay.saveState()
    card_path = overlay.beginPath()
    card_path.roundRect(card_x, card_y, card_width, card_height, 12)
    overlay.clipPath(card_path, fill=0, stroke=0)
    overlay.linearGradient(
        card_x,
        card_y,
        card_x + card_width,
        card_y,
        (HexColor("#a7f6e9"), HexColor("#edfaff")),
        (0, 1),
    )
    overlay.restoreState()
    _draw_fitted_line(overlay, page_height, "Nombre", 178.7, 86, 150, 8, "Helvetica", ink)
    _draw_fitted_line(
        overlay, page_height, fields.get("attendee_name", ""),
        178.7, 101, 225, 11, "Helvetica-Bold", ink,
    )
    _draw_fitted_line(overlay, page_height, "DNI", 460.7, 86, 45, 8, "Helvetica", ink)
    _draw_fitted_line(
        overlay, page_height, fields.get("attendee_dni", ""),
        460.7, 101, 47, 11, "Helvetica-Bold", ink,
    )
    _draw_fitted_line(overlay, page_height, "Tipo de entrada", 178.7, 123, 105, 8, "Helvetica", ink)
    _draw_fitted_line(
        overlay, page_height, fields.get("ticket_type", ""),
        178.7, 137, 130, 9, "Helvetica-Bold", ink,
    )
    if fields.get("row", "").strip():
        _draw_fitted_line(overlay, page_height, "Fila", 330, 123, 40, 8, "Helvetica", ink)
        _draw_fitted_line(overlay, page_height, fields.get("row", ""), 330, 137, 40, 9, "Helvetica-Bold", ink)
    if fields.get("seat", "").strip():
        _draw_fitted_line(overlay, page_height, "Asiento", 390, 123, 55, 8, "Helvetica", ink)
        _draw_fitted_line(overlay, page_height, fields.get("seat", ""), 390, 137, 55, 9, "Helvetica-Bold", ink)

    # Ficha del evento; la miniatura original queda intacta si no se carga una nueva.
    rect_from_top(99, 190, 470, 54, white)
    _draw_fitted_line(
        overlay, page_height, fields.get("event", ""),
        105, 197, 452, 12, "Helvetica-Bold", ink,
    )

    # Calendario, reloj y ubicación, como en la entrada Joinnus original.
    icon_color = _hex_color("#00b894")
    icon_top = 222.3
    icon_y = page_height - icon_top - 9
    overlay.setStrokeColorRGB(*icon_color)
    overlay.setLineWidth(1.15)
    overlay.roundRect(106, icon_y, 8.3, 8.2, 1.2, fill=0, stroke=1)
    overlay.line(108, icon_y + 9.7, 108, icon_y + 6.8)
    overlay.line(112.2, icon_y + 9.7, 112.2, icon_y + 6.8)
    overlay.line(106.2, icon_y + 5.7, 114.1, icon_y + 5.7)
    overlay.circle(224.3, icon_y + 4.2, 4.5, fill=0, stroke=1)
    overlay.line(224.3, icon_y + 4.2, 224.3, icon_y + 7.1)
    overlay.line(224.3, icon_y + 4.2, 226.4, icon_y + 3.1)
    pin_x = 291.8
    overlay.circle(pin_x, icon_y + 5.6, 4.1, fill=0, stroke=1)
    overlay.circle(pin_x, icon_y + 5.6, 1.1, fill=0, stroke=1)
    overlay.line(pin_x - 2.8, icon_y + 2.6, pin_x, icon_y - 1.2)
    overlay.line(pin_x + 2.8, icon_y + 2.6, pin_x, icon_y - 1.2)

    schedule_day = fields.get("day", "").strip().rstrip(".")
    schedule_date = f"{schedule_day}. {fields.get('date', '').strip()}".strip(". ")
    _draw_fitted_line(overlay, page_height, schedule_date, 119, 221, 96, 9.2, "Helvetica", muted)
    _draw_fitted_line(overlay, page_height, fields.get("time", ""), 233, 221, 52, 9.2, "Helvetica", muted)
    _draw_fitted_line(overlay, page_height, fields.get("location", ""), 301, 221, 256, 9.2, "Helvetica", muted)

    # Detalles de compra.
    rect_from_top(45, 250, 523, 115, white)
    overlay.setStrokeColorRGB(*_hex_color(border))
    overlay.setLineWidth(0.8)
    overlay.roundRect(49.2, page_height - 359.5, 513.6, 105.1, 6, fill=0, stroke=1)
    _draw_fitted_line(overlay, page_height, "Detalles de la compra", 60.8, 266, 180, 11, "Helvetica-Bold", ink)
    _draw_fitted_line(overlay, page_height, "Organizado por:", 60.8, 287, 130, 8, "Helvetica", muted)
    producer = fields.get("producer", "").strip()
    ruc = fields.get("ruc", "").strip()
    producer_line = f"{producer} - {ruc}" if ruc else producer
    _draw_fitted_line(overlay, page_height, producer_line, 60.8, 301, 235, 8.3, "Helvetica-Bold", ink)
    _draw_fitted_line(overlay, page_height, "Dirección del evento:", 60.8, 321, 135, 8, "Helvetica", muted)
    _draw_fitted_line(overlay, page_height, fields.get("address", ""), 60.8, 335, 235, 8.3, "Helvetica-Bold", ink)
    _draw_fitted_line(overlay, page_height, "Transacción", 307.4, 287, 80, 8, "Helvetica", muted)
    _draw_fitted_line(overlay, page_height, fields.get("transaction", ""), 307.4, 301, 108, 8, "Helvetica-Bold", ink)
    _draw_fitted_line(overlay, page_height, "Fecha de compra", 307.4, 321, 95, 8, "Helvetica", muted)
    _draw_fitted_line(overlay, page_height, fields.get("purchase_date", ""), 307.4, 335, 108, 8, "Helvetica-Bold", ink)
    _draw_fitted_line(overlay, page_height, "Precio de la entrada", 430.7, 287, 90, 8, "Helvetica", muted)
    _draw_fitted_line(overlay, page_height, fields.get("price", ""), 430.7, 303, 75, 8.3, "Helvetica-Bold", green)


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
    if template == "ticketmaster":
        _draw_ticketmaster_layout(overlay, height, fields, replace_identifiers)
    elif template == "joinnus":
        _draw_joinnus_layout(overlay, height, fields)
    if event_image:
        try:
            _draw_event_image(overlay, height, event_image, profile, image_mode)
        except (OSError, ValueError) as exc:
            raise ValueError("La imagen del evento no es válida.") from exc
    if reconstructed_qr:
        _draw_reconstructed_qr(overlay, height, reconstructed_qr, profile)
    if template == "teleticket":
        schedule = [
            f"{fields.get('day', '').strip()}, {fields.get('date', '').strip()}",
            fields.get("time", "").strip(),
        ]
        _draw_replacement(overlay, height, ticket_fields["schedule"], schedule)
        for name in ("location", "ticket_type", "row", "seat", "category", "event", "producer", "ruc", "price"):
            value = fields.get(name, "").strip()
            if name in {"row", "seat"}:
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
    if replace_identifiers and template in {"teleticket", "ticketmaster"}:
        if template == "teleticket":
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
                "ruc", "ticket_type", "row", "seat", "category", "address",
                "admission_type", "door", "service_charge", "total_price",
                "producer_address",
                "attendee_name", "attendee_dni", "transaction", "purchase_date",
                "purchase_number",
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
