import numpy as np
import zxingcpp

import src.pipeline as pipeline


def test_zxing_fallback_validates_when_opencv_cannot_read_clean_output(monkeypatch):
    barcode = zxingcpp.create_barcode("IqZAUAGS", zxingcpp.BarcodeFormat.QRCode)
    image = np.asarray(zxingcpp.write_barcode_to_image(barcode, 300))
    monkeypatch.setattr(pipeline, "_decode_with_scales", lambda detector, clean: "")

    result = pipeline.process_image(image)

    assert result.validated is True
    assert result.decoded_text == "IqZAUAGS"
    assert result.validation_text == "IqZAUAGS"


def test_confirmed_payload_is_reencoded_when_rectified_grid_is_damaged(monkeypatch):
    barcode = zxingcpp.create_barcode("tRVbapQ0", zxingcpp.BarcodeFormat.QRCode)
    image = np.asarray(zxingcpp.write_barcode_to_image(barcode, 300))
    damaged = np.full((464, 464), 255, dtype=np.uint8)
    monkeypatch.setattr(
        pipeline,
        "clean_straight_qr",
        lambda straight: (np.zeros((21, 21), dtype=np.uint8), damaged),
    )
    monkeypatch.setattr(pipeline, "_decode_with_scales", lambda detector, clean: "")

    result = pipeline.process_image(image)

    assert result.validated is True
    assert result.decoded_text == "tRVbapQ0"
    assert result.validation_text == "tRVbapQ0"
    assert result.method.endswith("+payload")

