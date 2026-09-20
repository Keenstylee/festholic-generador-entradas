from __future__ import annotations

import hashlib
from pathlib import Path
import re
import secrets

import cv2
import numpy as np
import streamlit as st

from src.pdf_editor import edit_ticket_fields, inspect_pdf, inspect_ticket_fields
from src.pdf_preview import pdf_page_count as count_pdf_pages
from src.pdf_preview import render_pdf_page as render_page_png
from src.pipeline import process_image
from src.reconstruction import encode_png


APP_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_PATH = APP_DIR / "assets" / "plantilla-teleticket.pdf"

st.set_page_config(page_title="Digitalizador de entradas | Festholic", page_icon="🎟️", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
    :root{--fh-bg:#09070f;--fh-panel:#11141d;--fh-input:#0c1018;--fh-text:#f7f7fb;--fh-muted:#9298a8;--fh-border:rgba(255,255,255,.09);--fh-violet:#9b5cff;--fh-pink:#ff3d9a}
    html,body,[data-testid="stAppViewContainer"],.stApp{background:var(--fh-bg);color:var(--fh-text);font-family:"Manrope",system-ui,sans-serif}
    [data-testid="stHeader"],#MainMenu,footer{display:none!important}
    [data-testid="stMainBlockContainer"]{width:100%;max-width:1480px;padding:18px 18px 44px}
    h1,h2,h3,[data-testid="stHeading"]{font-family:"Space Grotesk","Manrope",sans-serif;letter-spacing:-.025em}
    p,label,[data-testid="stCaptionContainer"]{color:var(--fh-muted)}
    .tool-identity{display:flex;align-items:center;gap:14px;min-width:0}
    .tool-icon{width:42px;height:42px;flex:0 0 auto;display:grid;place-items:center;border:1px solid rgba(155,92,255,.25);border-radius:12px;color:#d9c7ff;background:rgba(155,92,255,.10)}
    .tool-icon svg{width:21px;height:21px}.tool-identity h1{margin:0;color:#fff;font-size:23px;line-height:1.15}.tool-identity p{margin:5px 0 0;font-size:11px;line-height:1.4}
    .section-intro{margin-bottom:11px}.section-intro strong{display:block;color:#f8f8fb;font-size:13px}.section-intro span{display:block;margin-top:3px;color:var(--fh-muted);font-size:10px}.preview-marker{height:0;overflow:hidden}
    [data-testid="stVerticalBlockBorderWrapper"]{border:1px solid var(--fh-border)!important;border-radius:14px!important;background:linear-gradient(145deg,rgba(20,24,35,.96),rgba(12,15,23,.98))!important;box-shadow:0 10px 28px rgba(0,0,0,.18)}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.preview-marker){position:sticky;top:16px}
    [data-testid="stFileUploaderDropzone"]{min-height:106px;padding:16px!important;border:1px dashed rgba(132,143,166,.36)!important;border-radius:11px!important;background:rgba(8,11,18,.54)!important}
    [data-testid="stFileUploaderDropzone"]:hover{border-color:rgba(155,92,255,.62)!important}[data-testid="stFileUploaderFile"]{border:1px solid var(--fh-border);border-radius:10px;background:rgba(255,255,255,.025)}
    [data-baseweb="input"]>div,[data-baseweb="select"]>div{min-height:42px;border-color:var(--fh-border)!important;border-radius:10px!important;background:var(--fh-input)!important}
    [data-baseweb="input"]>div:focus-within,[data-baseweb="select"]>div:focus-within{border-color:rgba(155,92,255,.65)!important;box-shadow:0 0 0 2px rgba(155,92,255,.10)!important}
    [data-testid="stWidgetLabel"] p{color:#d6d8df;font-size:10px;font-weight:700}[data-testid="stImage"] img{border:1px solid rgba(255,255,255,.08);border-radius:10px}[data-testid="stAlert"]{border:1px solid var(--fh-border);border-radius:11px}hr{border-color:var(--fh-border)!important}
    .stButton>button,.stDownloadButton>button{min-height:42px;border-radius:10px!important;font-weight:800!important}.stButton>button[kind="secondary"]{border-color:var(--fh-border);color:#ececf2;background:rgba(255,255,255,.045)}
    .stButton>button[kind="secondary"]:hover{border-color:rgba(155,92,255,.38);background:rgba(155,92,255,.09)}
    .stDownloadButton>button[kind="primary"]{min-height:54px;border:0!important;background:linear-gradient(135deg,#6637ff,#ff32bf)!important;color:#fff!important;box-shadow:0 8px 24px rgba(133,57,255,.22)}
    .stDownloadButton>button[kind="primary"] *,.stDownloadButton>button[kind="primary"] p{color:#fff!important;opacity:1!important}.stDownloadButton>button[kind="primary"]:hover{filter:brightness(1.08);transform:translateY(-1px)}.stButton>button:disabled{opacity:.42}
    @media(max-width:900px){[data-testid="stMainBlockContainer"]{padding:12px 11px 36px}[data-testid="stHorizontalBlock"]{flex-wrap:wrap}[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{min-width:100%!important;width:100%!important}[data-testid="stVerticalBlockBorderWrapper"]:has(.preview-marker){position:static}.tool-identity h1{font-size:20px}}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def digitalize_qr(data: bytes):
    raw = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("El archivo no pudo interpretarse como una imagen válida.")
    return image, process_image(image)


def section_intro(title: str, description: str) -> None:
    st.markdown(f'<div class="section-intro"><strong>{title}</strong><span>{description}</span></div>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def pdf_page_count(data: bytes) -> int:
    return count_pdf_pages(data)


@st.cache_data(show_spinner=False)
def render_pdf_page(data: bytes, page_index: int, zoom: float) -> bytes:
    return render_page_png(data, page_index, zoom)


def new_ticket_identity() -> dict[str, str]:
    return {
        "number": str(10_000 + secrets.randbelow(90_000)),
        "code": "".join(str(secrets.randbelow(10)) for _ in range(16)),
    }


def rotate_ticket_identity() -> None:
    """Prepara identificadores nuevos después de entregar cada descarga."""
    st.session_state.ticket_identity = new_ticket_identity()


def safe_pdf_filename(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", value).strip().rstrip(".")
    if name.lower().endswith(".pdf"):
        name = name[:-4].strip().rstrip(".")
    return f"{name or 'entrada_digitalizada'}.pdf"


def render_pdf_preview(data: bytes | None) -> None:
    if not data:
        st.info("Selecciona un PDF para mostrar la vista previa.")
        return
    try:
        total_pages = pdf_page_count(data)
        document_key = hashlib.sha256(data).hexdigest()[:12]
        page_column, zoom_column = st.columns([1, 1.25])
        with page_column:
            page_number = st.selectbox(
                "Página",
                options=list(range(1, total_pages + 1)),
                key=f"preview_page_{document_key}",
            )
        with zoom_column:
            zoom = st.select_slider(
                "Zoom",
                options=[1.0, 1.25, 1.5, 1.75, 2.0],
                value=1.25,
                format_func=lambda value: f"{round(value * 100)}%",
                key="preview_zoom",
            )
        image = render_pdf_page(data, page_number - 1, zoom)
        st.image(image, caption=f"Página {page_number} de {total_pages}", use_container_width=True)
        st.caption("La vista se actualiza automáticamente. Usa el icono de ampliar de la imagen para verla en pantalla completa.")
    except (ValueError, RuntimeError) as error:
        st.error(f"No se pudo renderizar la vista previa: {error}", icon="🚨")


@st.dialog("Cómo usar el digitalizador")
def show_tutorial() -> None:
    st.markdown("""
    1. Selecciona la plantilla Teleticket o carga un PDF compatible.
    2. Sube una fotografía clara del QR físico, con los cuatro bordes visibles.
    3. Espera la validación y revisa que el contenido coincida.
    4. Actualiza los datos y la imagen del evento.
    5. Comprueba la vista previa y descarga la entrada digitalizada.

    El archivo original no se modifica.
    """)


with st.container(border=True):
    title_column, help_column = st.columns([8, 2], vertical_alignment="center")
    with title_column:
        st.markdown("""
        <div class="tool-identity"><span class="tool-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM18 18h3v3h-3zM18 14h3M14 20h2"/></svg></span><span><h1>Digitalizador de entradas</h1><p>Recupera y edita entradas digitales con la misma validez del código QR.</p></span></div>
        """, unsafe_allow_html=True)
    with help_column:
        if st.button("¿Cómo usar?", icon=":material/help_outline:", use_container_width=True):
            show_tutorial()


pdf_data: bytes | None = None
pdf_name = "plantilla-teleticket.pdf"
pdf_source = "Plantilla Teleticket"
qr_file = None
qr_png = None
qr_ready = False
qr_original = None
qr_result = None
qr_error = None
edited_pdf: bytes | None = None
generation_error = None

if "ticket_identity" not in st.session_state:
    st.session_state.ticket_identity = new_ticket_identity()
ticket_identity = st.session_state.ticket_identity

editor_column, preview_column = st.columns([7, 3], gap="small")

with editor_column:
    source_left, source_right = st.columns(2, gap="small")
    with source_left:
        with st.container(border=True):
            section_intro("PDF de la entrada", "Usa la plantilla Teleticket o sube un PDF compatible.")
            pdf_source = st.radio("Origen del documento", ["Plantilla Teleticket", "Subir otro PDF"], horizontal=True, label_visibility="collapsed", key="pdf_source")
            if pdf_source == "Plantilla Teleticket":
                if DEFAULT_TEMPLATE_PATH.exists():
                    pdf_data = DEFAULT_TEMPLATE_PATH.read_bytes()
                    st.success("plantilla-teleticket.pdf · PDF listo", icon="✅")
                else:
                    st.error("No se encontró la plantilla incluida.")
            else:
                pdf_file = st.file_uploader("Arrastra tu PDF aquí o selecciónalo", type=["pdf"], key="pdf_file", help="Se conservarán el diseño y los códigos de control.")
                if pdf_file is not None:
                    pdf_data = pdf_file.getvalue()
                    pdf_name = pdf_file.name
                    st.caption(f"{pdf_file.name} · {len(pdf_data)/(1024*1024):.2f} MB")

    with source_right:
        with st.container(border=True):
            section_intro("Fotografía del código QR", "Sube una foto clara del QR físico.")
            qr_file = st.file_uploader("Arrastra una imagen aquí o selecciónala", type=["jpg", "jpeg", "png", "bmp"], key="qr_file", help="Formatos JPG, PNG, JPEG o BMP.")
            if qr_file is not None:
                st.caption(f"{qr_file.name} · {len(qr_file.getvalue())/(1024*1024):.2f} MB")

    if qr_file is not None:
        try:
            with st.spinner("Analizando, reconstruyendo y validando el QR…"):
                qr_original, qr_result = digitalize_qr(qr_file.getvalue())
            if qr_result.success and qr_result.validated:
                qr_png = encode_png(qr_result.clean)
                qr_ready = True
        except ValueError as error:
            qr_error = str(error)

        with st.container(border=True):
            section_intro("Resultado del QR", "Comparación entre la fotografía y la matriz reconstruida.")
            if qr_error:
                st.error(qr_error, icon="🚨")
            elif qr_original is not None and qr_result is not None:
                original_column, arrow_column, result_column, status_column = st.columns([1.15, .25, 1.15, 1.6], vertical_alignment="center")
                with original_column:
                    st.caption("Imagen original")
                    st.image(cv2.cvtColor(qr_original, cv2.COLOR_BGR2RGB), use_container_width=True)
                with arrow_column:
                    st.markdown("<div style='text-align:center;color:#777f91;font-size:22px'>→</div>", unsafe_allow_html=True)
                with result_column:
                    st.caption("QR digitalizado")
                    if qr_result.success:
                        st.image(qr_result.clean, clamp=True, use_container_width=True)
                with status_column:
                    if qr_ready:
                        st.success("**QR válido**\n\n✓ QR detectado  \n✓ Reconstrucción completada  \n✓ Lectura exitosa  \n✓ Contenido coincide")
                    elif qr_result.success:
                        st.warning(qr_result.message, icon="⚠️")
                    else:
                        st.error(f"No se pudo validar.\n\n{qr_result.message}", icon="🚨")

    detected = None
    pdf_info = None
    if pdf_data is not None:
        try:
            pdf_info = inspect_pdf(pdf_data)
            detected = inspect_ticket_fields(pdf_data)
            if pdf_source == "Plantilla Teleticket" and detected["category"].isdigit():
                detected["category"] = "PRE-VENTA IBK"
        except (ValueError, RuntimeError) as error:
            st.error(str(error), icon="🚨")

    if detected is not None:
        with st.container(border=True):
            section_intro("Información del evento", f"Documento compatible · {pdf_info['pages']} página(s)")
            event_col, producer_col, ruc_col = st.columns([1.4, 1, .75])
            with event_col: event = st.text_input("Nombre del evento", detected["event"])
            with producer_col: producer = st.text_input("Productor", detected["producer"])
            with ruc_col: ruc = st.text_input("RUC", detected["ruc"], max_chars=11)
            st.divider()
            section_intro("Fecha y ubicación", "Información visible en la cabecera de la entrada.")
            day_col, date_col, time_col, location_col = st.columns([.7, .9, .8, 1.45])
            with day_col: day = st.text_input("Día", detected["day"])
            with date_col: date = st.text_input("Fecha", detected["date"])
            with time_col: time = st.text_input("Hora", detected["time"])
            with location_col: location = st.text_input("Lugar", detected["location"])
            st.divider()
            section_intro("Información de la entrada", "Sector, ubicación asignada y precio.")
            sector_col, category_col = st.columns(2)
            with sector_col: ticket_type = st.text_input("Sector", detected["ticket_type"])
            with category_col: category = st.text_input("Categoría", detected["category"])
            row_col, seat_col, price_col = st.columns(3)
            with row_col: row = st.text_input("Fila", detected["row"])
            with seat_col: seat = st.text_input("Asiento", detected["seat"])
            with price_col: price = st.text_input("Precio", detected["price"])
            st.divider()
            section_intro("Imagen del evento", "Reemplaza la fotografía o el logo de la plantilla.")
            image_preview_col, image_control_col = st.columns([1, 2.2], vertical_alignment="center")
            with image_control_col:
                event_image = st.file_uploader("Cambiar imagen", type=["png", "jpg", "jpeg", "webp"], key="event_image", help="Los PNG transparentes son ideales para logos.")
                image_mode_label = st.radio("Modo de imagen", ["Logo completo", "Rellenar espacio"], horizontal=True)
            with image_preview_col:
                if event_image is not None: st.image(event_image, caption="Imagen seleccionada", use_container_width=True)
                else: st.caption("Sin imagen nueva")

        if qr_ready:
            try:
                with st.spinner("Actualizando la vista previa…"):
                    edited_pdf = edit_ticket_fields(
                        pdf_data,
                        {"event":event,"day":day,"date":date,"time":time,"location":location,"ticket_type":ticket_type,"row":row,"seat":seat,"category":category,"producer":producer,"ruc":ruc,"price":price,"qr_number":ticket_identity["number"],"qr_code":ticket_identity["code"]},
                        event_image=event_image.getvalue() if event_image is not None else None,
                        image_mode="cover" if image_mode_label == "Rellenar espacio" else "contain",
                        reconstructed_qr=qr_png,
                    )
            except (ValueError, RuntimeError) as error:
                generation_error = str(error)

with preview_column:
    with st.container(border=True):
        st.markdown('<div class="preview-marker"></div>', unsafe_allow_html=True)
        section_intro("Vista previa de la entrada", "Así se verá el documento con la información actualizada.")
        render_pdf_preview(edited_pdf or pdf_data)
        if generation_error:
            st.error(generation_error, icon="🚨")
        elif edited_pdf is not None:
            download_name = st.text_input(
                "Nombre del PDF",
                value=f"digitalizada_{Path(pdf_name).stem}",
                key=f"download_name_{pdf_name}",
                help="Puedes escribir el nombre con o sin la extensión .pdf.",
            )
            st.caption(f"Identificadores de esta descarga: N° {ticket_identity['number']} · {ticket_identity['code']}")
            st.download_button("Descargar entrada digitalizada", data=edited_pdf, file_name=safe_pdf_filename(download_name), mime="application/pdf", type="primary", icon=":material/download:", use_container_width=True, on_click=rotate_ticket_identity)
            st.caption("Se generará un nuevo PDF sin modificar el archivo original.")
        else:
            st.button("Descargar entrada digitalizada", disabled=True, icon=":material/download:", use_container_width=True)
            st.caption("Selecciona el PDF y valida el QR para habilitar la descarga.")
