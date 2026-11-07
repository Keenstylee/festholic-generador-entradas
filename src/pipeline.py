from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import zxingcpp

from .preprocessing import preprocessing_variants
from .reconstruction import clean_straight_qr


@dataclass
class ReconstructionResult:
    success: bool
    message: str
    decoded_text: str = ""
    validation_text: str = ""
    validated: bool = False
    method: str = ""
    points: np.ndarray | None = None
    straight: np.ndarray | None = None
    matrix: np.ndarray | None = None
    clean: np.ndarray | None = None


def _detect(detector: cv2.QRCodeDetector, image: np.ndarray):
    text, points, straight = detector.detectAndDecode(image)
    return text or "", points, straight


def _decode_with_scales(detector: cv2.QRCodeDetector, image: np.ndarray) -> str:
    for factor in (1.0, 0.75, 1.5, 2.0):
        candidate = image if factor == 1 else cv2.resize(
            image, None, fx=factor, fy=factor, interpolation=cv2.INTER_NEAREST
        )
        text, _, _ = detector.detectAndDecode(candidate)
        if text:
            return text
    return ""


def _decode_with_zxing(image: np.ndarray) -> tuple[str, bytes]:
    """Segundo lector para QR con ECI u otros modos incompletos en OpenCV."""
    try:
        result = zxingcpp.read_barcode(image)
    except (ValueError, RuntimeError):
        return "", b""
    if result is None or not result.valid:
        return "", b""
    return result.text or "", bytes(result.bytes or b"")


def _reencode_with_zxing(payload: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Regenera una matriz limpia cuando dos lectores confirmaron el payload."""
    barcode = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode, "H")
    modules = np.asarray(
        zxingcpp.write_barcode_to_image(
            barcode,
            size_hint=0,
            with_hrt=False,
            with_quiet_zones=True,
        )
    ).astype(np.uint8)
    matrix = (modules[4:-4, 4:-4] < 128).astype(np.uint8)
    clean = cv2.resize(modules, None, fx=16, fy=16, interpolation=cv2.INTER_NEAREST)
    return matrix, clean


def process_image(image: np.ndarray) -> ReconstructionResult:
    if image is None or image.size == 0:
        return ReconstructionResult(False, "La imagen está vacía o no es válida.")

    detector = cv2.QRCodeDetector()
    best_geometry = None

    for name, candidate in preprocessing_variants(image):
        text, points, straight = _detect(detector, candidate)
        if points is not None and straight is not None and straight.size:
            best_geometry = (name, text, points, straight)
        if text and straight is not None and straight.size:
            best_geometry = (name, text, points, straight)
            break

    if best_geometry is None:
        return ReconstructionResult(
            False,
            "No se detectó una cuadrícula QR completa. Prueba una fotografía más cercana y con los cuatro bordes visibles.",
        )

    name, original_text, points, straight = best_geometry
    opencv_original_text = original_text
    matrix, clean = clean_straight_qr(straight)
    source_fallback_text, source_bytes = _decode_with_zxing(image)
    clean_fallback_text, clean_bytes = _decode_with_zxing(clean)
    original_text = original_text or source_fallback_text
    validation_text = _decode_with_scales(detector, clean) or clean_fallback_text
    if source_bytes and clean_bytes:
        validated = source_bytes == clean_bytes
    else:
        validated = bool(validation_text) and (
            not original_text or validation_text == original_text
        )

    # Algunas cámaras móviles suavizan los módulos: ambos lectores recuperan
    # el contenido original, pero la cuadrícula rectificada de OpenCV queda
    # inutilizable. Solo regeneramos cuando OpenCV y ZXing coinciden y el nuevo
    # QR vuelve a decodificar exactamente los mismos bytes.
    if (
        not validated
        and source_bytes
        and opencv_original_text
        and source_fallback_text == opencv_original_text
    ):
        rebuilt_matrix, rebuilt_clean = _reencode_with_zxing(source_bytes)
        rebuilt_text, rebuilt_bytes = _decode_with_zxing(rebuilt_clean)
        if rebuilt_bytes == source_bytes:
            matrix, clean = rebuilt_matrix, rebuilt_clean
            validation_text = rebuilt_text or source_fallback_text
            validated = True
            name = f"{name}+payload"

    if validated:
        message = "Reconstrucción completada y validada correctamente."
    elif not original_text and not validation_text:
        message = "Se reconstruyó la cuadrícula, pero no fue posible verificar su contenido."
    else:
        message = "La salida no superó la validación de contenido; no debe considerarse una reconstrucción final."

    return ReconstructionResult(
        success=True,
        message=message,
        decoded_text=original_text,
        validation_text=validation_text,
        validated=validated,
        method=name,
        points=points,
        straight=straight,
        matrix=matrix,
        clean=clean,
    )

