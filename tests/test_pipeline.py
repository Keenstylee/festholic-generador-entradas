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

