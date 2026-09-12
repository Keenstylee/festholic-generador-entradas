from __future__ import annotations

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


st.set_page_config(page_title="Generador de PDF", page_icon="▦", layout="wide")
st.title("Generador de PDF")
st.caption(
    "Completa los datos del evento, reemplaza su imagen y reconstruye el QR "
    "antes de insertarlo en la entrada."
)


@st.cache_data(show_spinner=False)
def digitalize_qr(data: bytes):
    raw = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("El archivo no pudo interpretarse como una imagen válida.")
    return image, process_image(image)


st.subheader("1. Archivos de entrada")
source_left, source_right = st.columns(2)
with source_left:
    pdf_file = st.file_uploader(
        "PDF base de la entrada",
        type=["pdf"],
        key="pdf_file",
        help="Se conservarán el diseño y los códigos de control del documento.",
    )
with source_right:
    qr_file = st.file_uploader(
        "Foto del QR físico",
        type=["jpg", "jpeg", "png", "bmp"],
        key="qr_file",
        help="El QR se corregirá, reconstruirá y validará automáticamente.",
    )

qr_png = None
qr_text = ""
qr_ready = False

if qr_file is not None:
    try:
        with st.spinner("Digitalizando y validando el QR…"):
            qr_original, qr_result = digitalize_qr(qr_file.getvalue())

        st.subheader("2. Digitalización del QR")
        original_column, result_column = st.columns(2)
        with original_column:
            st.markdown("**Fotografía cargada**")
            st.image(cv2.cvtColor(qr_original, cv2.COLOR_BGR2RGB), use_container_width=True)
        with result_column:
            st.markdown("**QR reconstruido**")
            if qr_result.success:
                st.image(qr_result.clean, clamp=True, use_container_width=True)

        if qr_result.success and qr_result.validated:
            qr_png = encode_png(qr_result.clean)
            qr_text = qr_result.validation_text
            qr_ready = True
            st.success("QR reconstruido y validado. Está listo para insertarse en el PDF.")
        elif qr_result.success:
            st.warning(qr_result.message)
        else:
            st.error(qr_result.message)
    except ValueError as error:
        st.error(str(error))
elif pdf_file is not None:
    st.info("Carga también la fotografía del QR para completar la entrada.")

if pdf_file is not None:
    pdf_data = pdf_file.getvalue()
    try:
        info = inspect_pdf(pdf_data)
        detected = inspect_ticket_fields(pdf_data)
        st.subheader("3. Datos del evento")
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

        st.subheader("4. Generar documento")
        if not qr_ready:
            st.warning("El botón se habilitará cuando el QR haya sido reconstruido y validado.")

        if st.button("Generar PDF completo", type="primary", disabled=not qr_ready):
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
                    "digitalizado y validado."
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
        st.error(str(error))
elif qr_file is None:
    st.info("Carga el PDF base y la fotografía del QR para comenzar.")
