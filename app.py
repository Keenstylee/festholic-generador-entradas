from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from src.pdf_editor import (
    edit_ticket_fields,
    inspect_pdf,
    inspect_ticket_fields,
)
from src.pipeline import process_image
from src.reconstruction import encode_png


APP_DIR = Path(__file__).resolve().parent
LOGO_PATH = APP_DIR / "assets" / "festholic.png"

st.set_page_config(
    page_title="Digitalizador de entradas | Festholic",
    page_icon="🎟️",
    layout="wide",
)


def _logo_data_uri() -> str:
    if not LOGO_PATH.exists():
        return ""
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');

    :root {
        --fh-bg: #09070f;
        --fh-surface: rgba(20, 16, 31, 0.82);
        --fh-surface-dark: #0b0e12;
        --fh-text: #ffffff;
        --fh-muted: #aaa3b8;
        --fh-border: rgba(255, 255, 255, 0.11);
        --fh-violet: #9b5cff;
        --fh-pink: #ff3d9a;
        --fh-cyan: #38d9ff;
        --fh-green: #51d98a;
        --fh-yellow: #ffd84d;
        --fh-coral: #ff625d;
    }

    html, body, [data-testid="stAppViewContainer"], .stApp {
        background: var(--fh-bg);
        color: var(--fh-text);
        font-family: "Manrope", system-ui, sans-serif;
    }

    [data-testid="stHeader"] { background: rgba(9, 7, 15, .76); }
    [data-testid="stToolbar"] { right: 1rem; }
    [data-testid="stMainBlockContainer"] {
        max-width: 1280px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    h1, h2, h3, [data-testid="stHeading"] {
        font-family: "Space Grotesk", "Manrope", sans-serif;
        letter-spacing: -.035em;
    }

    p, label, [data-testid="stCaptionContainer"] { color: var(--fh-muted); }

    .fh-brand {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-bottom: 1.25rem;
    }
    .fh-brand img { width: 148px; height: auto; object-fit: contain; }
    .fh-brand-copy { border-left: 1px solid var(--fh-border); padding-left: 1rem; }
    .fh-brand-copy > span {
        display: inline-flex;
        align-items: center;
        border: 1px solid rgba(155, 92, 255, .32);
        border-radius: 999px;
        padding: .3rem .65rem;
        color: #d9c7ff;
        background: rgba(155, 92, 255, .1);
        font-size: .74rem;
        font-weight: 800;
        letter-spacing: .04em;
        text-transform: uppercase;
    }
    .fh-brand-copy h1 { margin: .45rem 0 .2rem; color: #fff; font-size: clamp(1.9rem, 4vw, 3rem); }
    .fh-brand-copy p { margin: 0; max-width: 760px; }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid var(--fh-border) !important;
        border-radius: 16px !important;
        background: var(--fh-surface) !important;
        box-shadow: 0 18px 50px rgba(0, 0, 0, .18);
    }

    [data-testid="stFileUploaderDropzone"],
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div {
        background: var(--fh-surface-dark) !important;
        border-color: var(--fh-border) !important;
        border-radius: 13px !important;
    }

    [data-testid="stFileUploaderDropzone"]:hover,
    [data-baseweb="input"] > div:focus-within {
        border-color: rgba(155, 92, 255, .7) !important;
    }

    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"] {
        border: 0 !important;
        border-radius: 13px !important;
        background: linear-gradient(135deg, #9b5cff, #ff3d9a) !important;
        color: #fff !important;
        font-weight: 850 !important;
        transition: transform 170ms ease, filter 170ms ease !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stDownloadButton > button[kind="primary"]:hover {
        transform: translateY(-1px);
        filter: brightness(1.08);
        background: linear-gradient(135deg, #ad76ff, #ff4fa7) !important;
    }
    .stButton > button:disabled { opacity: .46; transform: none !important; }

    [data-testid="stAlert"] { border-radius: 13px; border: 1px solid var(--fh-border); }
    [data-testid="stImage"] img { border-radius: 14px; }
    hr { border-color: var(--fh-border) !important; }

    @media (max-width: 700px) {
        [data-testid="stMainBlockContainer"] { padding: 1rem .8rem 2.5rem; }
        .fh-brand { align-items: flex-start; }
        .fh-brand img { width: 104px; margin-top: .25rem; }
        .fh-brand-copy { padding-left: .75rem; }
        .fh-brand-copy h1 { font-size: 1.72rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

logo_uri = _logo_data_uri()
logo_html = f'<img src="{logo_uri}" alt="Festholic">' if logo_uri else ""
st.markdown(
    f"""
    <div class="fh-brand">
      {logo_html}
      <div class="fh-brand-copy">
        <span>Herramienta Festholic</span>
        <h1>Digitalizador de entradas</h1>
        <p>Reconstruye el código QR, actualiza la información del evento y genera una entrada lista para descargar.</p>
      </div>
    </div>
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


source_left, source_right = st.columns(2)
with source_left:
    with st.container(border=True):
        st.subheader("1. Subir PDF base")
        st.caption("Selecciona la entrada que conservará su diseño original.")
        pdf_file = st.file_uploader(
            "PDF base de la entrada",
            type=["pdf"],
            key="pdf_file",
            help="Se conservarán el diseño y los códigos de control del documento.",
        )
with source_right:
    with st.container(border=True):
        st.subheader("2. Subir código QR")
        st.caption("Carga una fotografía clara del código QR físico.")
        qr_file = st.file_uploader(
            "Fotografía del código QR",
            type=["jpg", "jpeg", "png", "bmp"],
            key="qr_file",
            help="El QR se corregirá, reconstruirá y validará automáticamente.",
        )

qr_png = None
qr_text = ""
qr_ready = False
qr_original = None
qr_result = None
qr_error = None

if qr_file is not None:
    try:
        with st.spinner("Digitalizando y validando el QR…"):
            qr_original, qr_result = digitalize_qr(qr_file.getvalue())
        if qr_result.success and qr_result.validated:
            qr_png = encode_png(qr_result.clean)
            qr_text = qr_result.validation_text
            qr_ready = True
    except ValueError as error:
        qr_error = str(error)


def render_qr_preview() -> None:
    st.subheader("4. Vista previa")
    if qr_error:
        st.error(qr_error, icon="🚨")
        return
    if qr_original is None or qr_result is None:
        st.info("Carga una fotografía para visualizar y validar el QR reconstruido.")
        return

    original_column, result_column = st.columns(2)
    with original_column:
        st.markdown("**Fotografía cargada**")
        st.image(cv2.cvtColor(qr_original, cv2.COLOR_BGR2RGB), use_container_width=True)
    with result_column:
        st.markdown("**QR reconstruido**")
        if qr_result.success:
            st.image(qr_result.clean, clamp=True, use_container_width=True)

    if qr_ready:
        st.success("QR reconstruido y validado. Está listo para insertarse en el PDF.", icon="✅")
    elif qr_result.success:
        st.warning(qr_result.message, icon="⚠️")
    else:
        st.error(qr_result.message, icon="🚨")

if pdf_file is not None:
    pdf_data = pdf_file.getvalue()
    try:
        info = inspect_pdf(pdf_data)
        detected = inspect_ticket_fields(pdf_data)
        with st.container(border=True):
            st.subheader("3. Datos editables del evento")
            st.caption(f"Plantilla cargada correctamente: {info['pages']} página(s).")

            event_image = st.file_uploader(
                "Foto o logo del evento (opcional)",
                type=["png", "jpg", "jpeg", "webp"],
                key="event_image",
                help="Un PNG transparente funciona mejor para logos.",
            )
            image_mode_label = st.radio(
                "Ajuste de la imagen",
                ["Logo completo", "Rellenar todo el espacio"],
                horizontal=True,
            )
            if event_image is not None:
                st.image(event_image, caption="Imagen que se insertará", width=280)

            left, right = st.columns(2)
            with left:
                event = st.text_input("Evento", detected["event"])
                day = st.text_input("Día", detected["day"])
                date = st.text_input("Fecha", detected["date"])
                time = st.text_input("Año y hora", detected["time"])
                location = st.text_input("Ubicación", detected["location"])
            with right:
                ticket_type = st.text_input("Tipo de entrada / sector", detected["ticket_type"])
                row = st.text_input("Número de fila", detected["row"])
                seat = st.text_input("Número de asiento", detected["seat"])
                category = st.text_input("Categoría", detected["category"])

        with st.container(border=True):
            render_qr_preview()

        with st.container(border=True):
            st.subheader("5. Generar y descargar PDF")
            if not qr_ready:
                st.warning("El botón se habilitará cuando el QR haya sido reconstruido y validado.", icon="⚠️")

            if st.button("Digitalizar entrada y generar PDF", type="primary", disabled=not qr_ready):
                with st.spinner("Eliminando el QR anterior e insertando el QR digitalizado…"):
                    edited = edit_ticket_fields(
                        pdf_data,
                        {
                            "event": event,
                            "day": day,
                            "date": date,
                            "time": time,
                            "location": location,
                            "ticket_type": ticket_type,
                            "row": row,
                            "seat": seat,
                            "category": category,
                        },
                        event_image=event_image.getvalue() if event_image is not None else None,
                        image_mode="cover" if image_mode_label == "Rellenar todo el espacio" else "contain",
                        reconstructed_qr=qr_png,
                    )
                    st.session_state["generated_pdf"] = edited
                    st.session_state["generated_pdf_name"] = f"generado_{pdf_file.name}"
                    st.success(
                        "PDF generado: el QR anterior fue eliminado y sustituido por el QR "
                        "digitalizado y validado.",
                        icon="✅",
                    )

            if "generated_pdf" in st.session_state:
                st.download_button(
                    "Descargar PDF generado",
                    data=st.session_state["generated_pdf"],
                    file_name=st.session_state["generated_pdf_name"],
                    mime="application/pdf",
                    type="primary",
                )
    except (ValueError, RuntimeError) as error:
        st.error(str(error), icon="🚨")
elif qr_file is not None:
    with st.container(border=True):
        render_qr_preview()
    st.info("Carga también el PDF base para completar la entrada.")
else:
    st.info("Carga el PDF base y la fotografía del QR para comenzar.")
