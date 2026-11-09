from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
from streamlit.testing.v1 import AppTest


def authorized_app(app_path: Path) -> AppTest:
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"allowed":true,"user":{"email":"test@festholic.com"}}'
    response.__exit__.return_value = False
    with patch("urllib.request.urlopen", return_value=response):
        app = AppTest.from_file(str(app_path), default_timeout=30)
        app.query_params["festholic_token"] = "signed-test-token"
        return app.run()


def test_direct_access_without_festholic_token_is_blocked():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()

    assert not app.segmented_control
    assert any("ACCESO PRIVADO" in str(element.value) for element in app.markdown)
    assert not app.exception


def test_batch_mode_without_uploaded_qrs_keeps_preview_available():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = authorized_app(app_path)

    app.segmented_control(key="generation_mode").set_value("Varias entradas").run()

    assert app.segmented_control(key="generation_mode").value == "Varias entradas"
    assert not app.exception


def test_valid_batch_qr_renders_original_and_rebuilt_comparison():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    qr = cv2.QRCodeEncoder_create().encode("festholic-batch-comparison")
    qr = cv2.resize(qr, None, fx=10, fy=10, interpolation=cv2.INTER_NEAREST)
    encoded, png = cv2.imencode(".png", qr)
    assert encoded

    app = authorized_app(app_path)
    app.segmented_control(key="generation_mode").set_value("Varias entradas").run()
    app.file_uploader(key="qr_files").set_value(
        [("entrada-01.png", png.tobytes(), "image/png")]
    ).run(timeout=30)

    comparisons = [element.value for element in app.markdown if 'class="batch-qr-result__body"' in str(element.value)]
    assert comparisons
    assert "QR físico" in comparisons[0]
    assert "Digitalizado" in comparisons[0]
    assert not app.exception
