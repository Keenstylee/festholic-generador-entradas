from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_batch_mode_without_uploaded_qrs_keeps_preview_available():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()

    app.segmented_control(key="generation_mode").set_value("Varias entradas").run()

    assert app.segmented_control(key="generation_mode").value == "Varias entradas"
    assert not app.exception
