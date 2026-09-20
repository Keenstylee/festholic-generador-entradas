from __future__ import annotations

import pymupdf


def pdf_page_count(data: bytes) -> int:
    """Devuelve la cantidad de páginas de un PDF recibido en memoria."""
    with pymupdf.open(stream=data, filetype="pdf") as document:
        return document.page_count


def render_pdf_page(data: bytes, page_index: int, zoom: float = 1.25) -> bytes:
    """Renderiza una página como PNG para evitar visores PDF anidados."""
    with pymupdf.open(stream=data, filetype="pdf") as document:
        if page_index < 0 or page_index >= document.page_count:
            raise ValueError("La página solicitada no existe.")
        page = document.load_page(page_index)
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pixmap.tobytes("png")
