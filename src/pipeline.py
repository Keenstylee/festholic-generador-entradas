from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

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
    matrix, clean = clean_straight_qr(straight)
    validation_text = _decode_with_scales(detector, clean)
    validated = bool(validation_text) and (
        not original_text or validation_text == original_text
    )

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

