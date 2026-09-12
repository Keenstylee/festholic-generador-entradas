from __future__ import annotations

import cv2
import numpy as np


VALID_SIZES = tuple(21 + 4 * index for index in range(40))


def nearest_qr_size(size: int) -> int:
    return min(VALID_SIZES, key=lambda candidate: abs(candidate - size))


def clean_straight_qr(straight: np.ndarray, scale: int = 16, quiet_zone: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Convierte la vista rectificada en una matriz binaria y una imagen limpia."""
    if straight is None or straight.size == 0:
        raise ValueError("No existe una vista rectificada para reconstruir.")

    if straight.ndim == 3:
        straight = cv2.cvtColor(straight, cv2.COLOR_BGR2GRAY)

    side = nearest_qr_size(min(straight.shape[:2]))
    sampled = cv2.resize(straight, (side, side), interpolation=cv2.INTER_AREA)
    _, binary = cv2.threshold(sampled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    matrix = (binary < 128).astype(np.uint8)

    modules = np.where(matrix == 1, 0, 255).astype(np.uint8)
    modules = np.pad(modules, quiet_zone, mode="constant", constant_values=255)
    clean = cv2.resize(modules, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    return matrix, clean


def encode_png(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("No fue posible generar el archivo PNG.")
    return encoded.tobytes()

