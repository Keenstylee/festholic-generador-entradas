import numpy as np

from src.reconstruction import VALID_SIZES, clean_straight_qr, nearest_qr_size


def test_valid_qr_sizes():
    assert VALID_SIZES[0] == 21
    assert VALID_SIZES[-1] == 177
    assert len(VALID_SIZES) == 40


def test_nearest_size():
    assert nearest_qr_size(22) == 21
    assert nearest_qr_size(32) == 33


def test_clean_output_has_quiet_zone_and_binary_values():
    source = np.full((21, 21), 255, dtype=np.uint8)
    source[0:7, 0:7] = 0
    matrix, clean = clean_straight_qr(source, scale=2, quiet_zone=4)
    assert matrix.shape == (21, 21)
    assert clean.shape == (58, 58)
    assert set(np.unique(clean)).issubset({0, 255})
    assert np.all(clean[:8, :] == 255)

