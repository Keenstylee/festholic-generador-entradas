from __future__ import annotations

import cv2
import numpy as np


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image.copy()
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def preprocessing_variants(image: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Genera variantes sin destruir la imagen original."""
    gray = to_gray(image)
    denoised = cv2.bilateralFilter(gray, 7, 50, 50)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised)
    adaptive = cv2.adaptiveThreshold(
        clahe,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        7,
    )
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    sharpened = cv2.addWeighted(clahe, 1.5, cv2.GaussianBlur(clahe, (0, 0), 1.2), -0.5, 0)
    return [
        ("original", image),
        ("gris", gray),
        ("contraste_CLAHE", clahe),
        ("binarizacion_adaptativa", adaptive),
        ("binarizacion_Otsu", otsu),
        ("enfoque_moderado", sharpened),
    ]

