#!/usr/bin/env python3
"""post-fire-recovery — 火后植被恢复监测

分两步监测火灾后的植被动态：

- **烧伤严重度（dNBR）**：归一化烧伤比 NBR=(NIR−SWIR)/(NIR+SWIR)，
  差分 dNBR=NBR_pre−NBR_post。按 USGS/Key 2006 关键阈值分为五级
  （unburned / low / moderate_low / moderate_high / high）。
- **植被恢复**：火后多期 NDVI 时间序列追踪恢复轨迹——
  线性斜率（正 = 恢复中）、恢复年限（NDVI 首次回到火前基线 × target 的期数，
  未在观测期内恢复记 −1）、以及逐期空间平均 NDVI 曲线。

数据源：本地多波段 GeoTIFF（波段顺序 nir_pre/swir_pre/nir_post/swir_post/
ndvi_prefire + n_dates 个火后 NDVI），或 ``--synthetic`` 生成含不同烧伤严重度
与恢复速率的物理一致场景（离线）。

隐私声明 / Privacy：默认离线，不访问网络，所有处理本地完成。

Usage:
    python post-fire-recovery.py --input scene.tif --n-dates 6 --output-dir ./out
    python post-fire-recovery.py --bbox 118 34 119 35 --synthetic --n-dates 6 --output-dir ./out

License: MIT
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

VERSION = "1.0.0"
SKILL_NAME = "post-fire-recovery"

try:
    from _geoskill_core.errors import (
        GeoSkillError, UsageError, ValidationError, ProcessError, to_exit_code,
    )
    from _geoskill_core.manifest import OutputManifest, OutputFile
except ImportError:  # pragma: no cover
    class GeoSkillError(Exception):
        def __init__(self, message: str, code: int = 7, kind: str = "EGeo", **kw):
            super().__init__(message)
            self.message, self.code, self.kind = message, code, kind

    class UsageError(GeoSkillError):
        def __init__(self, m, **k): super().__init__(m, code=2, kind="EUsage", **k)

    class ValidationError(GeoSkillError):
        def __init__(self, m, **k): super().__init__(m, code=6, kind="EValidate", **k)

    class ProcessError(GeoSkillError):
        def __init__(self, m, **k): super().__init__(m, code=7, kind="EProcess", **k)

    def to_exit_code(exc):
        return getattr(exc, "code", 7)

    OutputManifest = None
    OutputFile = None


# dNBR 严重度关键阈值（USGS / Key et al. 2006）
DNBR_BREAKS = [0.10, 0.27, 0.44, 0.66]
SEVERITY_NAMES = ["unburned", "low", "moderate_low", "moderate_high", "high"]

# 输入波段顺序
IDX_NIR_PRE, IDX_SWIR_PRE, IDX_NIR_POST, IDX_SWIR_POST, IDX_NDVI_PRE = 0, 1, 2, 3, 4
IDX_NDVI_POST_START = 5

DEFAULT_RECOVERY_TARGET = 0.95     # NDVI 恢复到火前基线的比例
NODATA_RECOVERY_YEAR = -1.0


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def validate_bbox(bbox: List[float], source: str = "bbox") -> None:
    """Validate geographic bbox: W<=E, S<=N, lon/lat in range, min area.

    Cross-dateline (W>E) is a ValidationError with a hint to split.
    """
    if bbox is None or len(bbox) != 4:
        raise ValidationError(f"{source}: expected 4 floats [W S E N], got {bbox!r}")
    try:
        w, s, e, n = (float(v) for v in bbox)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{source}: non-numeric bbox values: {bbox!r}") from exc
    for v, name in ((w, "W"), (s, "S"), (e, "E"), (n, "N")):
        if not (v == v):
            raise ValidationError(f"{source}: bbox contains NaN at {name}")
    if not (-180.0 <= w <= 180.0 and -180.0 <= e <= 180.0):
        raise ValidationError(f"{source}: lon out of [-180,180]: W={w} E={e}")
    if not (-90.0 <= s <= 90.0 and -90.0 <= n <= 90.0):
        raise ValidationError(f"{source}: lat out of [-90,90]: S={s} N={n}")
    if w > e:
        raise ValidationError(
            f"{source}: W ({w}) > E ({e}); cross-dateline bboxes are not supported. "
            "Split into two bboxes on each side of the 180\u00b0 meridian and run separately."
        )
    if s > n:
        raise ValidationError(f"{source}: S ({s}) > N ({n})")
    if (e - w) < 1e-9 or (n - s) < 1e-9:
        raise ValidationError(
            f"{source}: bbox too small (dlon={e - w}, dlat={n - s}); need > 1e-9 degrees"
        )


# ---------------------------------------------------------------------------
# 烧伤指数
# ---------------------------------------------------------------------------
def nbr_index(nir: np.ndarray, swir: np.ndarray) -> np.ndarray:
    """归一化烧伤比 NBR = (NIR − SWIR) / (NIR + SWIR)。"""
    nir = nir.astype(np.float32)
    swir = swir.astype(np.float32)
    denom = nir + swir
    out = np.zeros_like(denom, dtype=np.float32)
    valid = denom != 0
    out[valid] = (nir[valid] - swir[valid]) / denom[valid]
    return np.clip(out, -1.0, 1.0)


def dnbr_index(nir_pre: np.ndarray, swir_pre: np.ndarray,
               nir_post: np.ndarray, swir_post: np.ndarray) -> np.ndarray:
    """差分 NBR：dNBR = NBR_pre − NBR_post。"""
    return (nbr_index(nir_pre, swir_pre) - nbr_index(nir_post, swir_post)).astype(np.float32)


def classify_severity(dnbr: np.ndarray) -> np.ndarray:
    """dNBR → 严重度等级 (0=unburned … 4=high)。"""
    grade = np.zeros(dnbr.shape, dtype=np.uint8)
    grade[dnbr >= DNBR_BREAKS[0]] = 1
    grade[dnbr >= DNBR_BREAKS[1]] = 2
    grade[dnbr >= DNBR_BREAKS[2]] = 3
    grade[dnbr >= DNBR_BREAKS[3]] = 4
    return grade


def severity_areas(grade: np.ndarray, pixel_area_m2: float) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for g, name in enumerate(SEVERITY_NAMES):
        px = int((grade == g).sum())
        out[name] = {"pixels": px, "area_ha": px * pixel_area_m2 / 10000.0,
                     "fraction": float(px) / grade.size}
    return out


# ---------------------------------------------------------------------------
# 恢复分析
# ---------------------------------------------------------------------------
def recovery_slope(ndvi_series: np.ndarray) -> np.ndarray:
    """火后 NDVI 序列的每像元线性斜率（正 = 恢复中）。"""
    n = ndvi_series.shape[0]
    if n < 2:
        raise ValidationError(f"recovery slope needs >=2 dates, got {n}", n_dates=int(n))
    t = np.arange(n, dtype=np.float64)
    t = t - t.mean()
    denom = float((t ** 2).sum())
    y = ndvi_series - ndvi_series.mean(axis=0, keepdims=True)
    return ((t[:, None, None] * y).sum(axis=0) / denom).astype(np.float32)


def recovery_year(ndvi_series: np.ndarray, baseline: np.ndarray,
                  target_frac: float = DEFAULT_RECOVERY_TARGET) -> np.ndarray:
    """每像元 NDVI 首次达到 baseline×target_frac 的期号；未达到记 −1。"""
    n = ndvi_series.shape[0]
    target = baseline.astype(np.float32) * float(target_frac)
    out = np.full(ndvi_series.shape[1:], NODATA_RECOVERY_YEAR, dtype=np.float32)
    reached = np.zeros(ndvi_series.shape[1:], dtype=bool)
    for k in range(n):
        hit = (ndvi_series[k] >= target) & (~reached)
        out[hit] = float(k)
        reached |= hit
    return out


def recovery_trajectory(ndvi_series: np.ndarray,
                        mask: Optional[np.ndarray] = None) -> List[float]:
    """逐期空间平均 NDVI（可选仅在 mask 内统计）。"""
    traj: List[float] = []
    for k in range(ndvi_series.shape[0]):
        layer = ndvi_series[k]
        if mask is not None:
            vals = layer[mask.astype(bool)]
            traj.append(float(vals.mean()) if vals.size > 0 else float("nan"))
        else:
            traj.append(float(layer.mean()))
    return traj


# ---------------------------------------------------------------------------
# 输入拆分
# ---------------------------------------------------------------------------
def split_inputs(cube: np.ndarray, n_dates: int
                 ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray,
                            np.ndarray, np.ndarray]:
    """拆分为 (nir_pre, swir_pre, nir_post, swir_post, ndvi_pre, ndvi_post_series)。"""
    need = IDX_NDVI_POST_START + n_dates
    if cube.ndim != 3 or cube.shape[0] < need:
        raise ValidationError(
            f"input needs >= {need} bands (4 burn + ndvi_pre + {n_dates} post NDVI), "
            f"got shape {cube.shape}", shape=str(cube.shape), need=int(need))
    return (cube[IDX_NIR_PRE], cube[IDX_SWIR_PRE], cube[IDX_NIR_POST],
            cube[IDX_SWIR_POST], cube[IDX_NDVI_PRE],
            cube[IDX_NDVI_POST_START:IDX_NDVI_POST_START + n_dates])


# ---------------------------------------------------------------------------
# 合成数据
# ---------------------------------------------------------------------------
def generate_synthetic_series(
    bbox: List[float],
    n_dates: int = 6,
    width: int = 128,
    height: int = 128,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """生成含三种烧伤情形的场景。

    区域（自上而下）：未烧伤（稳定）、中度烧伤（观测期内恢复）、
    重度烧伤（观测期内未恢复）。
    返回 (cube, severity_truth_mask, info)。
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width]
    yyn = yy.astype(np.float32) / max(height - 1, 1)

    moderate = (yyn > 0.35) & (yyn < 0.55)
    high = (yyn > 0.70)

    # 火前 NBR：全场景茂密植被 ~0.70
    nbr_pre = np.full((height, width), 0.70, dtype=np.float32)
    # 火后 NBR：未烧 0.68，中度 0.35，重度 -0.08
    nbr_post = np.full((height, width), 0.68, dtype=np.float32)
    nbr_post[moderate] = 0.35
    nbr_post[high] = -0.08

    # 由 NBR 反推一致的光谱（NBR=(nir-swir)/(nir+swir)，取 nir+swir=0.5）
    s = 0.5
    nir_pre = ((1 + nbr_pre) * s / 2).astype(np.float32)
    swir_pre = ((1 - nbr_pre) * s / 2).astype(np.float32)
    nir_post = ((1 + nbr_post) * s / 2).astype(np.float32)
    swir_post = ((1 - nbr_post) * s / 2).astype(np.float32)

    # 火前 NDVI 基线
    ndvi_pre = np.full((height, width), 0.70, dtype=np.float32)

    # 火后 NDVI 序列
    frac = np.arange(n_dates, dtype=np.float32) / max(n_dates - 1, 1)
    ndvi_post = np.zeros((n_dates, height, width), dtype=np.float32)
    for k in range(n_dates):
        layer = np.full((height, width), 0.70, dtype=np.float32)  # 未烧稳定
        layer[moderate] = 0.30 + (0.72 - 0.30) * frac[k]          # 恢复至基线
        layer[high] = 0.08 + (0.40 - 0.08) * frac[k]              # 恢复缓慢
        layer += rng.normal(0, 0.004, size=layer.shape).astype(np.float32)
        ndvi_post[k] = np.clip(layer, 0.0, 1.0)

    cube = np.concatenate(
        [np.stack([nir_pre, swir_pre, nir_post, swir_post, ndvi_pre], axis=0),
         ndvi_post], axis=0).astype(np.float32)

    truth = np.zeros((height, width), dtype=np.uint8)
    truth[moderate] = 2     # moderate_low
    truth[high] = 4         # high
    info = {
        "bbox": bbox, "width": width, "height": height, "n_dates": n_dates,
        "moderate_px": int(moderate.sum()), "high_px": int(high.sum()),
    }
    return cube, truth, info


def pixel_area_m2(bbox: List[float], height: int, width: int) -> float:
    lat0 = (bbox[1] + bbox[3]) / 2.0
    x_m = (bbox[2] - bbox[0]) * 111320.0 * np.cos(np.deg2rad(lat0)) / max(width, 1)
    y_m = (bbox[3] - bbox[1]) * 110540.0 / max(height, 1)
    return float(abs(x_m * y_m))


# ---------------------------------------------------------------------------
# GeoTIFF I/O
# ---------------------------------------------------------------------------
def write_geotiff(path: str, cube: np.ndarray, bbox: List[float],
                  nodata: float = -9999.0) -> None:
    import rasterio
    from rasterio.transform import from_bounds

    if cube.ndim == 2:
        cube = cube[np.newaxis, ...]
    nb, h, w = cube.shape
    transform = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], w, h)
    profile = {
        "driver": "GTiff", "height": h, "width": w, "count": nb,
        "dtype": "float32", "crs": "EPSG:4326", "transform": transform,
        "nodata": nodata, "compress": "deflate",
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        for b in range(nb):
            dst.write(cube[b].astype("float32"), b + 1)


def read_geotiff(path: str) -> Tuple[np.ndarray, List[float]]:
    import rasterio
    if not os.path.exists(path):
        raise UsageError(f"input raster not found: {path}", path=path)
    with rasterio.open(path) as src:
        cube = src.read().astype(np.float32)
        b = src.bounds
        bbox = [b.left, b.bottom, b.right, b.top]
    return cube, bbox


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def write_manifest(output_dir, args, outputs, qa, started_at, exit_code, bbox) -> Optional[str]:
    if OutputManifest is None:
        return None
    cmd = " ".join([SKILL_NAME] + sys.argv[1:])
    man = OutputManifest(
        skill=SKILL_NAME, skill_version=VERSION, command=cmd,
        started_at=started_at, finished_at=_utc_now(), exit_code=exit_code,
        inputs={
            "input": getattr(args, "input", None),
            "synthetic": bool(getattr(args, "synthetic", False)),
            "n_dates": int(getattr(args, "n_dates", 6)),
            "recovery_target": float(getattr(args, "recovery_target", DEFAULT_RECOVERY_TARGET)),
        },
        outputs=[OutputFile(**o) for o in outputs], qa=qa,
        software={"python": sys.version.split()[0], "skill": SKILL_NAME},
    )
    path = os.path.join(output_dir, "output-manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(man.to_dict(), f, ensure_ascii=False, indent=2, default=str)
    return path


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def process(args: argparse.Namespace) -> int:
    started_at = _utc_now()
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    bbox = list(args.bbox) if args.bbox else None

    # Validate CLI params up-front
    if not isinstance(args.n_dates, int) or args.n_dates < 2:
        raise ValidationError(
            f"--n-dates must be an integer >= 2 (got {args.n_dates!r}); "
            "the recovery-slope OLS needs at least 2 time steps"
        )
    if not (0.0 < float(args.recovery_target) <= 1.0):
        raise ValidationError(
            f"--recovery-target must be in (0, 1] (got {args.recovery_target})"
        )

    synth_info: Optional[Dict[str, Any]] = None
    truth: Optional[np.ndarray] = None
    if args.input and not args.synthetic:
        cube, file_bbox = read_geotiff(args.input)
        bbox = bbox if bbox is not None else file_bbox
        # Replace NoData sentinel with NaN so nbr/dNBR don't see -9999 as
        # valid NIR/SWIR reflectance (which would force nbr=0 and dNBR=0
        # in NoData regions, silently mis-classifying them as "unburned").
        import rasterio as _rio
        with _rio.open(args.input) as _src:
            _nd = _src.nodata
        if _nd is not None:
            cube = np.where(cube == _nd, np.nan, cube).astype(np.float32)
        if not np.isfinite(cube).any():
            raise ValidationError(
                f"input raster '{args.input}' contains only NoData pixels; nothing to assess"
            )
        source_note = args.input
    else:
        if bbox is None:
            raise UsageError("provide --bbox (synthetic mode) or --input <raster>")
        validate_bbox(bbox, source="--bbox")
        cube, truth, synth_info = generate_synthetic_series(bbox, n_dates=args.n_dates)
        source_note = "synthetic"

    if cube.size == 0:
        raise ValidationError("input raster is empty")

    # If --bbox is also given with --input, validate the user-supplied bbox
    if bbox is not None and args.bbox is not None:
        validate_bbox(bbox, source="--bbox")

    nir_pre, swir_pre, nir_post, swir_post, ndvi_pre, ndvi_post = split_inputs(
        cube, args.n_dates)
    h, w = ndvi_pre.shape
    px_area = pixel_area_m2(bbox, h, w)

    # NaN safety: a pixel is valid iff nir_pre/swir_pre/nir_post/swir_post
    # and ALL post-fire NDVI are finite. (ndvi_pre is allowed to be NaN —
    # recovery_year handles that as "no baseline" by treating the target
    # as 0 which trivially holds; we instead mask those pixels separately.)
    finite_burn = (np.isfinite(nir_pre) & np.isfinite(swir_pre)
                   & np.isfinite(nir_post) & np.isfinite(swir_post))
    finite_ndvi = np.isfinite(ndvi_pre) & np.isfinite(ndvi_post).all(axis=0)
    finite = finite_burn & finite_ndvi
    n_valid = int(finite.sum())
    if n_valid < 1:
        raise ValidationError(
            f"need at least 1 valid (non-NoData) pixel; got {n_valid}"
        )

    # Replace NaN inputs with 0 inside arithmetic to avoid propagating NaN
    # to neighbors in dNBR / NBR / recovery_slope computations; we will mask
    # the outputs back to a sentinel at the end.
    def _safe(a: np.ndarray) -> np.ndarray:
        return np.where(finite, a, 0.0).astype(np.float32)

    nir_pre_s, swir_pre_s = _safe(nir_pre), _safe(swir_pre)
    nir_post_s, swir_post_s = _safe(nir_post), _safe(swir_post)
    ndvi_pre_s = _safe(ndvi_pre)
    ndvi_post_s = np.where(finite[np.newaxis, :, :], ndvi_post, 0.0).astype(np.float32)

    # 1) 严重度
    dnbr = dnbr_index(nir_pre_s, swir_pre_s, nir_post_s, swir_post_s)
    severity = classify_severity(dnbr)
    areas = severity_areas(severity, px_area)

    # 2) 恢复
    slope = recovery_slope(ndvi_post_s)
    rec_year = recovery_year(ndvi_post_s, ndvi_pre_s, target_frac=args.recovery_target)
    burn_mask = (severity >= 1) & finite
    traj_all = recovery_trajectory(ndvi_post_s, mask=finite)
    traj_burn = recovery_trajectory(ndvi_post_s, mask=burn_mask)

    # Mask NoData pixels in the output arrays (write them to a sentinel
    # that the user can identify downstream).
    severity = np.where(finite, severity, 255).astype(np.uint8)
    dnbr_out = np.where(finite, dnbr, -9999.0).astype(np.float32)
    rec_year_out = np.where(finite, rec_year, NODATA_RECOVERY_YEAR).astype(np.float32)
    slope_out = np.where(finite, slope, -9999.0).astype(np.float32)

    # 写出
    sev_tif = os.path.join(output_dir, "burn_severity.tif")
    write_geotiff(sev_tif, severity.astype(np.float32), bbox, nodata=255)

    dnbr_tif = os.path.join(output_dir, "dnbr.tif")
    write_geotiff(dnbr_tif, dnbr_out, bbox, nodata=-9999.0)

    year_tif = os.path.join(output_dir, "recovery_year.tif")
    write_geotiff(year_tif, rec_year_out, bbox, nodata=NODATA_RECOVERY_YEAR)

    slope_tif = os.path.join(output_dir, "recovery_slope.tif")
    write_geotiff(slope_tif, slope_out, bbox, nodata=-9999.0)

    # NaN-aware stats over valid pixels only
    valid_dnbr = dnbr[finite]
    valid_rec = rec_year[finite]
    stats = {
        "n_dates": int(args.n_dates),
        "recovery_target": float(args.recovery_target),
        "pixel_area_m2": px_area,
        "severity_areas": areas,
        "mean_dnbr": float(np.mean(valid_dnbr)) if valid_dnbr.size else 0.0,
        "trajectory_all": traj_all,
        "trajectory_burn_only": traj_burn,
        "recovered_fraction": float((valid_rec >= 0).mean()) if valid_rec.size else 0.0,
    }
    stats_path = os.path.join(output_dir, "recovery_trajectory.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    qa: Dict[str, Any] = {
        "source": source_note,
        "n_dates": int(args.n_dates),
        "mean_dnbr": stats["mean_dnbr"],
        "recovered_fraction": stats["recovered_fraction"],
        "trajectory_increasing": bool(traj_burn[-1] > traj_burn[0]) if len(traj_burn) > 1 else False,
        "n_valid_pixels": int(finite.sum()),
        "n_total_pixels": int(finite.size),
    }
    if synth_info is not None and truth is not None:
        # Accuracy only on valid pixels
        sev_valid = severity[finite]
        truth_valid = truth[finite]
        qa["synthetic_severity_accuracy"] = float((sev_valid == truth_valid).mean())

    outputs = [
        {"path": sev_tif, "kind": "raster", "crs_epsg": 4326,
         "bbox_wgs84": bbox, "band_count": 1},
        {"path": dnbr_tif, "kind": "raster", "crs_epsg": 4326,
         "bbox_wgs84": bbox, "band_count": 1},
        {"path": year_tif, "kind": "raster", "crs_epsg": 4326,
         "bbox_wgs84": bbox, "band_count": 1},
        {"path": slope_tif, "kind": "raster", "crs_epsg": 4326,
         "bbox_wgs84": bbox, "band_count": 1},
        {"path": stats_path, "kind": "json"},
    ]
    man_path = write_manifest(output_dir, args, outputs, qa, started_at, 0, bbox)

    if not args.quiet:
        print(f"[{SKILL_NAME}] source: {source_note}")
        print(f"[{SKILL_NAME}] dates: {args.n_dates}  mean dNBR: {stats['mean_dnbr']:.3f}")
        for name in SEVERITY_NAMES:
            print(f"[{SKILL_NAME}]   {name:>14}: {areas[name]['pixels']:>6} px  "
                  f"{areas[name]['area_ha']:.1f} ha")
        print(f"[{SKILL_NAME}] burn-only NDVI trajectory: "
              f"{[round(v, 3) for v in traj_burn]}")
        print(f"[{SKILL_NAME}] recovered fraction: {stats['recovered_fraction']*100:.1f}%")
        print(f"[{SKILL_NAME}] output: {sev_tif}")
        if man_path:
            print(f"[{SKILL_NAME}] manifest: {man_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=SKILL_NAME,
        description="Post-fire vegetation recovery from dNBR severity and NDVI time series.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                   help="geographic extent [minLon minLat maxLon maxLat]")
    p.add_argument("--input", help="input cube GeoTIFF (burn bands + ndvi_pre + post NDVI)")
    p.add_argument("--n-dates", type=int, default=6,
                   help="number of post-fire epochs (default: 6)")
    p.add_argument("--recovery-target", type=float, default=DEFAULT_RECOVERY_TARGET,
                   help=f"fraction of pre-fire baseline for recovery (default: {DEFAULT_RECOVERY_TARGET})")
    p.add_argument("--synthetic", action="store_true",
                   help="generate a physics-consistent synthetic burn scene (offline)")
    p.add_argument("--output-dir", default="./output", help="output directory")
    p.add_argument("--quiet", action="store_true", help="suppress console output")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return process(args)
    except GeoSkillError as exc:
        print(f"[{SKILL_NAME}] ERROR [{exc.kind}] {exc.message}", file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"[{SKILL_NAME}] ERROR {exc}", file=sys.stderr)
        return to_exit_code(exc)


if __name__ == "__main__":
    sys.exit(main())
