from pathlib import Path

import cv2
from streamlit.testing.v1 import AppTest


def test_batch_mode_without_uploaded_qrs_keeps_preview_available():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()

    app.segmented_control(key="generation_mode").set_value("Varias entradas").run()

    assert app.segmented_control(key="generation_mode").value == "Varias entradas"
    assert not app.exception


def test_valid_batch_qr_renders_original_and_rebuilt_comparison():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    qr = cv2.QRCodeEncoder_create().encode("festholic-batch-comparison")
    qr = cv2.resize(qr, None, fx=10, fy=10, interpolation=cv2.INTER_NEAREST)
    encoded, png = cv2.imencode(".png", qr)
    assert encoded

    app = AppTest.from_file(str(app_path), default_timeout=30).run()
    app.segmented_control(key="generation_mode").set_value("Varias entradas").run()
    app.file_uploader(key="qr_files").set_value(
        [("entrada-01.png", png.tobytes(), "image/png")]
    ).run(timeout=30)

    comparisons = [
        element.value
        for element in app.markdown
        if str(element.value).startswith('<div class="batch-qr-compare__title">')
    ]
    assert comparisons
    assert "QR reconstruido y validado" in comparisons[0]
    assert not app.exception
