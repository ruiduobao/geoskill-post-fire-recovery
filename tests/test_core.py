"""Core algorithm tests for post-fire-recovery."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))
from conftest import mod as pf


class TestNBR:
    def test_vegetation_high(self):
        nir = np.full((4, 4), 0.50, dtype=np.float32)
        swir = np.full((4, 4), 0.10, dtype=np.float32)
        nbr = pf.nbr_index(nir, swir)
        assert np.allclose(nbr, 0.4 / 0.6, atol=1e-5)
        assert nbr.mean() > 0.5

    def test_burned_low(self):
        nir = np.full((4, 4), 0.10, dtype=np.float32)
        swir = np.full((4, 4), 0.30, dtype=np.float32)
        assert pf.nbr_index(nir, swir).mean() < 0

    def test_zero_denominator_safe(self):
        z = np.zeros((3, 3), dtype=np.float32)
        assert np.all(pf.nbr_index(z, z) == 0)


class TestDNBR:
    def test_burn_yields_positive(self):
        # healthy pre, burned post
        nir_pre = np.full((4, 4), 0.50, dtype=np.float32)
        swir_pre = np.full((4, 4), 0.10, dtype=np.float32)
        nir_post = np.full((4, 4), 0.10, dtype=np.float32)
        swir_post = np.full((4, 4), 0.30, dtype=np.float32)
        dnbr = pf.dnbr_index(nir_pre, swir_pre, nir_post, swir_post)
        assert dnbr.mean() > 0.5


class TestSeverity:
    def test_class_boundaries(self):
        d = np.array([[-0.1, 0.05, 0.15, 0.30, 0.50, 0.70]], dtype=np.float32)
        g = pf.classify_severity(d)
        assert g.tolist() == [[0, 0, 1, 2, 3, 4]]

    def test_areas_sum_to_one(self):
        g = np.array([[0, 1, 2, 3], [4, 0, 1, 2]], dtype=np.uint8)
        areas = pf.severity_areas(g, pixel_area_m2=100.0)
        total_frac = sum(v["fraction"] for v in areas.values())
        assert abs(total_frac - 1.0) < 1e-9
        assert areas["high"]["pixels"] == 1


class TestRecovery:
    def test_slope_positive_for_increasing(self):
        n = 6
        series = np.zeros((n, 3, 3), dtype=np.float32)
        for k in range(n):
            series[k] = 0.1 + 0.1 * k  # 0.1..0.6
        slope = pf.recovery_slope(series)
        assert np.allclose(slope, 0.1, atol=1e-5)

    def test_slope_too_few_dates_raises(self):
        with pytest.raises(pf.ValidationError):
            pf.recovery_slope(np.zeros((1, 3, 3), dtype=np.float32))

    def test_recovery_year_first_hit(self):
        baseline = np.full((2, 2), 0.70, dtype=np.float32)
        series = np.zeros((4, 2, 2), dtype=np.float32)
        series[0] = 0.30
        series[1] = 0.50
        series[2] = 0.70  # target = 0.665 -> reached at index 2
        series[3] = 0.75
        year = pf.recovery_year(series, baseline, target_frac=0.95)
        assert np.all(year == 2.0)

    def test_recovery_year_never_reached(self):
        baseline = np.full((2, 2), 0.70, dtype=np.float32)
        series = np.zeros((3, 2, 2), dtype=np.float32)
        series[0] = 0.10; series[1] = 0.20; series[2] = 0.30
        year = pf.recovery_year(series, baseline, target_frac=0.95)
        assert np.all(year == pf.NODATA_RECOVERY_YEAR)

    def test_trajectory_means(self):
        series = np.zeros((2, 2, 2), dtype=np.float32)
        series[0] = 0.2; series[1] = 0.6
        traj = pf.recovery_trajectory(series)
        assert traj == pytest.approx([0.2, 0.6])


class TestSplitInputs:
    def test_too_few_bands_raises(self):
        cube = np.zeros((4, 8, 8), dtype=np.float32)
        with pytest.raises(pf.ValidationError):
            pf.split_inputs(cube, n_dates=6)

    def test_split_shape(self):
        cube = np.zeros((11, 8, 8), dtype=np.float32)  # 5 + 6
        out = pf.split_inputs(cube, n_dates=6)
        assert out[5].shape == (6, 8, 8)


class TestSynthetic:
    def test_shape(self):
        cube, truth, info = pf.generate_synthetic_series([118, 34, 119, 35], n_dates=6)
        assert cube.shape == (11, 128, 128)
        assert truth.shape == (128, 128)

    def test_severity_matches_injection(self):
        cube, truth, info = pf.generate_synthetic_series([118, 34, 119, 35], n_dates=6)
        nir_pre, swir_pre, nir_post, swir_post, ndvi_pre, ndvi_post = pf.split_inputs(cube, 6)
        dnbr = pf.dnbr_index(nir_pre, swir_pre, nir_post, swir_post)
        severity = pf.classify_severity(dnbr)
        assert (severity == truth).mean() > 0.99

    def test_recovery_pattern(self):
        cube, truth, info = pf.generate_synthetic_series([118, 34, 119, 35], n_dates=6)
        _, _, _, _, ndvi_pre, ndvi_post = pf.split_inputs(cube, 6)
        year = pf.recovery_year(ndvi_post, ndvi_pre, target_frac=0.95)
        moderate = truth == 2
        high = truth == 4
        # moderate recovers within window, high does not
        assert (year[moderate] >= 0).all()
        assert (year[high] < 0).all()
        # burn-only trajectory increases over time
        burn = truth >= 1
        traj = pf.recovery_trajectory(ndvi_post, mask=burn)
        assert traj[-1] > traj[0]


class TestGeoTiffIO:
    def test_roundtrip(self, tmp_path):
        cube = np.random.uniform(0, 1, (3, 16, 16)).astype(np.float32)
        bbox = [118.0, 34.0, 119.0, 35.0]
        path = str(tmp_path / "t.tif")
        pf.write_geotiff(path, cube, bbox)
        back, rb = pf.read_geotiff(path)
        assert back.shape == cube.shape
        np.testing.assert_allclose(rb, bbox, atol=1e-6)

    def test_read_missing_raises(self):
        with pytest.raises(pf.UsageError):
            pf.read_geotiff("/nonexistent/x.tif")
