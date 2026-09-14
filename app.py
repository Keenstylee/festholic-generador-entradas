from __future__ import annotations

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
DEFAULT_TEMPLATE_PATH = APP_DIR / "assets" / "plantilla-teleticket.pdf"

st.set_page_config(
    page_title="Digitalizador de entradas | Festholic",
    page_icon="🎟️",
    layout="wide",
)


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
        padding-top: .8rem;
        padding-bottom: 4rem;
    }

    h1, h2, h3, [data-testid="stHeading"] {
        font-family: "Space Grotesk", "Manrope", sans-serif;
        letter-spacing: -.035em;
    }

    p, label, [data-testid="stCaptionContainer"] { color: var(--fh-muted); }

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
    .stDownloadButton > button[kind="primary"] *,
    .stDownloadButton > button[kind="primary"] p {
        color: #ffffff !important;
        opacity: 1 !important;
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
        [data-testid="stMainBlockContainer"] { padding: .65rem .8rem 2.5rem; }
    }
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


pdf_data = None
pdf_name = "plantilla-teleticket.pdf"

source_left, source_right = st.columns(2)
with source_left:
    with st.container(border=True):
        st.subheader("1. Subir PDF base")
        st.caption("Usa la plantilla incluida o selecciona otro diseño de entrada.")
        pdf_source = st.radio(
            "Plantilla del documento",
            ["Plantilla Teleticket", "Subir otro PDF"],
            horizontal=True,
            key="pdf_source",
        )
        if pdf_source == "Plantilla Teleticket":
            if DEFAULT_TEMPLATE_PATH.exists():
                pdf_data = DEFAULT_TEMPLATE_PATH.read_bytes()
                st.success("Plantilla Teleticket seleccionada.", icon="✅")
            else:
                st.error("No se encontró la plantilla Teleticket incluida.", icon="🚨")
        else:
            pdf_file = st.file_uploader(
                "PDF base de la entrada",
                type=["pdf"],
                key="pdf_file",
                help="Se conservarán el diseño y los códigos de control del documento.",
            )
            if pdf_file is not None:
                pdf_data = pdf_file.getvalue()
                pdf_name = pdf_file.name
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

if pdf_data is not None:
    try:
        info = inspect_pdf(pdf_data)
        detected = inspect_ticket_fields(pdf_data)
        # La plantilla incluida tiene una categoría textual. Esta salvaguarda evita
        # que una sesión antigua de Streamlit conserve como categoría el N.º de orden.
        if pdf_source == "Plantilla Teleticket" and detected["category"].isdigit():
            detected["category"] = "PRE-VENTA IBK"
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
                producer = st.text_input("Productor del evento", detected["producer"])
                price = st.text_input("Precio", detected["price"])

        with st.container(border=True):
            render_qr_preview()

        with st.container(border=True):
            st.subheader("5. Generar y descargar PDF")
            if not qr_ready:
                st.info("Sube una fotografía válida del QR para preparar la entrada digitalizada.")
            else:
                try:
                    with st.spinner("Preparando la entrada digitalizada…"):
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
                                "producer": producer,
                                "price": price,
                            },
                            event_image=event_image.getvalue() if event_image is not None else None,
                            image_mode="cover" if image_mode_label == "Rellenar todo el espacio" else "contain",
                            reconstructed_qr=qr_png,
                        )
                    st.success("Entrada digitalizada lista para descargar.", icon="✅")
                    st.download_button(
                        "Descargar entrada digitalizada",
                        data=edited,
                        file_name=f"digitalizada_{pdf_name}",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                    )
                except (ValueError, RuntimeError) as error:
                    st.error(str(error), icon="🚨")
    except (ValueError, RuntimeError) as error:
        st.error(str(error), icon="🚨")
elif qr_file is not None:
    with st.container(border=True):
        render_qr_preview()
    st.info("Carga también el PDF base para completar la entrada.")
else:
    st.info("Carga el PDF base y la fotografía del QR para comenzar.")
