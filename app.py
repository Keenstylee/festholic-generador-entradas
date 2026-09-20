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
    :root{--fh-bg:#242426;--fh-deep:#0f1015;--fh-panel:#15161b;--fh-card:#1b1b22;--fh-card-deep:#121319;--fh-input:#181920;--fh-text:#fff;--fh-muted:#bbb6c2;--fh-faint:#918d99;--fh-border:rgba(255,255,255,.10);--fh-pink:#ff2e9f;--fh-orange:#ff7043;--fh-cyan:#25c9e8;--fh-green:#51d98a}
    html,body,[data-testid="stAppViewContainer"],.stApp{background:var(--fh-bg);color:var(--fh-text);font-family:"Manrope",system-ui,sans-serif}
    [data-testid="stAppViewContainer"]{position:relative;isolation:isolate;background:radial-gradient(circle at 108% 4%,rgba(37,201,232,.075) 0 110px,transparent 111px),radial-gradient(circle at -8% 88%,rgba(255,46,159,.045) 0 150px,transparent 151px),var(--fh-bg)}
    [data-testid="stAppViewContainer"]::before{content:"";position:fixed;z-index:0;right:-170px;top:24%;width:360px;height:360px;border:46px solid rgba(37,201,232,.035);border-radius:50%;pointer-events:none}
    [data-testid="stHeader"],#MainMenu,footer{display:none!important}
    [data-testid="stMainBlockContainer"]{position:relative;z-index:1;width:100%;max-width:1440px;padding:18px 18px 44px}
    h1,h2,h3,[data-testid="stHeading"]{font-family:"Space Grotesk","Manrope",sans-serif;letter-spacing:-.03em}
    p,label,[data-testid="stCaptionContainer"]{color:var(--fh-muted)}
    .tool-identity{display:flex;align-items:center;gap:13px;min-width:0;padding:10px 0 14px}
    .tool-icon{width:34px;height:42px;flex:0 0 auto;display:grid;place-items:center;color:var(--fh-cyan);background:transparent}
    .tool-icon svg{width:26px;height:26px}.tool-identity h1{margin:0;color:#fff;font-size:clamp(28px,3vw,34px);font-weight:800;line-height:1.05}.tool-identity p{margin:7px 0 0;color:var(--fh-muted);font-size:12px;line-height:1.5}
    .section-intro{position:relative;margin:2px 0 15px;padding-left:0}.section-intro strong{display:block;color:#f8f8fb;font-family:"Space Grotesk","Manrope",sans-serif;font-size:16px;font-weight:750;letter-spacing:-.02em}.section-intro span{display:block;margin-top:4px;color:var(--fh-muted);font-size:10.5px;line-height:1.45}
    .section-intro--accent{padding-left:13px;margin-top:4px;margin-bottom:17px}.section-intro--accent::before{content:"";position:absolute;left:0;top:2px;bottom:2px;width:3px;border-radius:3px}.section-intro--pink::before{background:var(--fh-pink);box-shadow:0 0 12px rgba(255,46,159,.20)}.section-intro--cyan::before{background:var(--fh-cyan);box-shadow:0 0 12px rgba(37,201,232,.18)}.section-intro--orange::before{background:var(--fh-orange);box-shadow:0 0 12px rgba(255,112,67,.18)}
    .preview-marker,.card-accent,.image-upload-marker{height:0;overflow:hidden}
    [data-testid="stVerticalBlockBorderWrapper"]{position:relative;overflow:hidden;border:1px solid var(--fh-border)!important;border-radius:18px!important;background:radial-gradient(circle at 94% 5%,rgba(37,201,232,.045),transparent 8rem),linear-gradient(135deg,var(--fh-card),var(--fh-card-deep))!important;box-shadow:0 16px 34px rgba(0,0,0,.22),inset 0 1px 0 rgba(255,255,255,.035)}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent)::before{content:"";position:absolute;z-index:2;left:0;top:20%;width:3px;height:60%;border-radius:0 3px 3px 0}.st-key-pdf_card::before,[data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent--pdf)::before{background:var(--fh-pink);box-shadow:0 0 13px rgba(255,46,159,.22)}.st-key-qr_card::before,[data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent--qr)::before{background:var(--fh-cyan);box-shadow:0 0 13px rgba(37,201,232,.20)}.st-key-preview_card::before,[data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent--preview)::before{background:var(--fh-orange);box-shadow:0 0 13px rgba(255,112,67,.20)}
    [data-testid="stHorizontalBlock"]:has(.st-key-pdf_card):has(.st-key-qr_card){align-items:stretch!important}[data-testid="stHorizontalBlock"]:has(.st-key-pdf_card):has(.st-key-qr_card)>[data-testid="stColumn"]{display:flex!important;align-self:stretch!important}[data-testid="stHorizontalBlock"]:has(.st-key-pdf_card):has(.st-key-qr_card)>[data-testid="stColumn"]>div{width:100%;height:100%}.st-key-pdf_card,.st-key-qr_card{width:100%;height:100%;min-height:268px}.st-key-pdf_card>[data-testid="stVerticalBlock"],.st-key-qr_card>[data-testid="stVerticalBlock"]{height:100%}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.tool-identity){position:relative;overflow:visible;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.tool-identity)::after{content:"";position:absolute;left:0;bottom:2px;width:156px;height:2px;border-radius:2px;background:linear-gradient(90deg,#ff2e9f 0 38%,#ff7043 38% 68%,#25c9e8 68% 100%);opacity:.9}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.preview-marker){position:sticky;top:16px;background:radial-gradient(circle at 94% 5%,rgba(255,112,67,.055),transparent 9rem),linear-gradient(145deg,#18191f,#101116)!important}
    [data-testid="stFileUploaderDropzone"]{min-height:118px;padding:16px!important;border:1px dashed rgba(37,201,232,.35)!important;border-radius:14px!important;background:rgba(37,201,232,.045)!important;display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:10px!important;text-align:center!important;transition:border-color .16s ease,background .16s ease,transform .16s ease}
    [data-testid="stFileUploaderDropzone"]:hover{border-color:rgba(37,201,232,.62)!important;background:rgba(37,201,232,.075)!important;transform:translateY(-1px)}
    [data-testid="stFileUploaderDropzone"] svg{width:30px!important;height:30px!important;color:var(--fh-cyan)!important;fill:var(--fh-cyan)!important}[data-testid="stFileUploaderDropzoneInstructions"]{text-align:center!important}[data-testid="stFileUploaderDropzoneInstructions"] span{color:#fff!important;font-weight:750!important}[data-testid="stFileUploaderDropzoneInstructions"] small{display:block!important;margin-top:3px!important;color:var(--fh-muted)!important;white-space:normal!important}
    [data-testid="stFileUploaderDropzone"] button{min-width:168px!important;min-height:40px!important;border-color:rgba(37,201,232,.30)!important;background:rgba(37,201,232,.14)!important;color:var(--fh-cyan)!important;font-size:0!important}[data-testid="stFileUploaderDropzone"] button>*{display:none!important}[data-testid="stFileUploaderDropzone"] button::after{content:"Seleccionar archivo";display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:800}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent--pdf) [data-testid="stFileUploaderDropzone"] button::after{content:"Seleccionar PDF"}[data-testid="stVerticalBlockBorderWrapper"]:has(.card-accent--qr) [data-testid="stFileUploaderDropzone"] button::after{content:"Cargar fotografía"}
    .st-key-event_image_upload [data-testid="stFileUploaderDropzone"]{border-color:rgba(255,112,67,.34)!important;background:rgba(255,112,67,.045)!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"]:hover{border-color:rgba(255,112,67,.60)!important;background:rgba(255,112,67,.075)!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"] svg{color:var(--fh-orange)!important;fill:var(--fh-orange)!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"] button{border-color:rgba(255,112,67,.30)!important;background:rgba(255,112,67,.14)!important;color:var(--fh-orange)!important}.st-key-event_image_upload [data-testid="stFileUploaderDropzone"] button::after{content:"Cambiar imagen"}
    [data-testid="stFileUploaderFile"]{border:1px solid var(--fh-border);border-radius:12px;background:rgba(255,255,255,.025)}
    .template-ready-zone{min-height:118px;display:flex;align-items:center;gap:12px;padding:16px;border:1px solid rgba(81,217,138,.25);border-radius:14px;background:rgba(81,217,138,.12);color:#dffbec;font-size:13px;font-weight:700}.template-ready-zone__icon{width:30px;height:30px;flex:0 0 auto;display:grid;place-items:center;border-radius:9px;background:rgba(81,217,138,.16);color:var(--fh-green);font-size:18px}.template-ready-zone small{display:block;margin-top:4px;color:rgba(223,251,236,.64);font-size:10px;font-weight:600}
    [data-baseweb="input"]>div,[data-baseweb="select"]>div{min-height:42px;border-color:rgba(255,255,255,.09)!important;border-radius:11px!important;background:var(--fh-input)!important}
    [data-baseweb="input"]>div:focus-within,[data-baseweb="select"]>div:focus-within{border-color:rgba(37,201,232,.55)!important;box-shadow:0 0 0 3px rgba(37,201,232,.10)!important}
    [role="radiogroup"] label:has(input:checked){color:var(--fh-cyan)!important}
    [data-testid="stWidgetLabel"] p{color:#ddd9e2;font-size:10px;font-weight:750}[data-testid="stImage"] img{border:1px solid rgba(255,255,255,.10);border-radius:14px}[data-testid="stAlert"]{border:1px solid var(--fh-border);border-radius:14px;background:rgba(18,19,25,.88)!important}hr{border-color:rgba(255,255,255,.065)!important;margin:20px 0!important}
    .stButton>button,.stDownloadButton>button{min-height:42px;border-radius:13px!important;font-weight:800!important}.stButton>button[kind="secondary"]{border-color:var(--fh-border);color:#ececf2;background:#17181e}
    .stButton>button[kind="secondary"]:hover{border-color:rgba(37,201,232,.28);color:var(--fh-cyan);background:rgba(37,201,232,.10)}
    .stDownloadButton>button[kind="primary"]{min-height:54px;border:0!important;background:#ff2e9f!important;color:#fff!important;box-shadow:0 10px 24px rgba(255,46,159,.23),inset 0 1px 0 rgba(255,255,255,.18)}
    .stDownloadButton>button[kind="primary"] *,.stDownloadButton>button[kind="primary"] p{color:#fff!important;opacity:1!important}.stDownloadButton>button[kind="primary"]:hover{filter:brightness(1.08);transform:translateY(-1px)}.stButton>button:disabled{opacity:1!important;border-color:rgba(255,255,255,.06)!important;background:#2a2b31!important;color:#777b84!important}
    @media(max-width:900px){[data-testid="stMainBlockContainer"]{padding:12px 11px 36px}[data-testid="stHorizontalBlock"]{flex-wrap:wrap}[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{min-width:100%!important;width:100%!important}[data-testid="stVerticalBlockBorderWrapper"]:has(.preview-marker){position:static}.tool-identity{padding-top:4px}.tool-identity h1{font-size:28px}}
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


def section_intro(title: str, description: str, accent: str | None = None) -> None:
    accent_class = f" section-intro--accent section-intro--{accent}" if accent else ""
    st.markdown(
        f'<div class="section-intro{accent_class}"><strong>{title}</strong><span>{description}</span></div>',
        unsafe_allow_html=True,
    )


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


with st.container(border=False):
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

editor_column, preview_column = st.columns([66, 34], gap="medium")

with editor_column:
    source_left, source_right = st.columns(2, gap="small")
    with source_left:
        with st.container(border=True, key="pdf_card"):
            st.markdown('<div class="card-accent card-accent--pdf"></div>', unsafe_allow_html=True)
            section_intro("PDF de la entrada", "Usa la plantilla Teleticket o sube un PDF compatible.")
            pdf_source = st.radio("Origen del documento", ["Plantilla Teleticket", "Subir otro PDF"], horizontal=True, label_visibility="collapsed", key="pdf_source")
            if pdf_source == "Plantilla Teleticket":
                if DEFAULT_TEMPLATE_PATH.exists():
                    pdf_data = DEFAULT_TEMPLATE_PATH.read_bytes()
                    st.markdown(
                        '<div class="template-ready-zone"><span class="template-ready-zone__icon">✓</span><span>plantilla-teleticket.pdf<small>Plantilla cargada y lista para editar</small></span></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.error("No se encontró la plantilla incluida.")
            else:
                pdf_file = st.file_uploader("Arrastra tu PDF aquí o selecciónalo", type=["pdf"], key="pdf_file", help="Se conservarán el diseño y los códigos de control.")
                if pdf_file is not None:
                    pdf_data = pdf_file.getvalue()
                    pdf_name = pdf_file.name
                    st.caption(f"{pdf_file.name} · {len(pdf_data)/(1024*1024):.2f} MB")

    with source_right:
        with st.container(border=True, key="qr_card"):
            st.markdown('<div class="card-accent card-accent--qr"></div>', unsafe_allow_html=True)
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
            section_intro("Resultado del QR", "Comparación entre la fotografía y la matriz reconstruida.", "cyan")
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
            section_intro("Información del evento", f"Documento compatible · {pdf_info['pages']} página(s)", "pink")
            event_col, producer_col, ruc_col = st.columns([1.4, 1, .75])
            with event_col: event = st.text_input("Nombre del evento", detected["event"])
            with producer_col: producer = st.text_input("Productor", detected["producer"])
            with ruc_col: ruc = st.text_input("RUC", detected["ruc"], max_chars=11)
            st.divider()
            section_intro("Fecha y ubicación", "Información visible en la cabecera de la entrada.", "cyan")
            day_col, date_col, time_col, location_col = st.columns([.7, .9, .8, 1.45])
            with day_col: day = st.text_input("Día", detected["day"])
            with date_col: date = st.text_input("Fecha", detected["date"])
            with time_col: time = st.text_input("Hora", detected["time"])
            with location_col: location = st.text_input("Lugar", detected["location"])
            st.divider()
            section_intro("Información de la entrada", "Sector, ubicación asignada y precio.", "orange")
            sector_col, category_col = st.columns(2)
            with sector_col: ticket_type = st.text_input("Sector", detected["ticket_type"])
            with category_col: category = st.text_input("Categoría", detected["category"])
            row_col, seat_col, price_col = st.columns(3)
            with row_col: row = st.text_input("Fila", detected["row"])
            with seat_col: seat = st.text_input("Asiento", detected["seat"])
            with price_col: price = st.text_input("Precio", detected["price"])
            st.divider()
            section_intro("Imagen del evento", "Reemplaza la fotografía o el logo de la plantilla.", "orange")
            image_preview_col, image_control_col = st.columns([1, 2.2], vertical_alignment="center")
            with image_control_col:
                with st.container(key="event_image_upload"):
                    st.markdown('<div class="image-upload-marker"></div>', unsafe_allow_html=True)
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
    with st.container(border=True, key="preview_card"):
        st.markdown('<div class="preview-marker card-accent card-accent--preview"></div>', unsafe_allow_html=True)
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
