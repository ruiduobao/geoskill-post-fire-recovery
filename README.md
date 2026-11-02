# Post-Fire Vegetation Recovery Monitoring (geoskill-post-fire-recovery)

> Uses dNBR (NIR/SWIR differenced normalized burn ratio) to classify five burn-severity levels, and combines multi-temporal post-fire NDVI recovery curves to estimate recovery trajectory, recovery slope, and recovery time, outputting a severity GeoTIFF, a recovery-trajectory JSON, and a recovery-time raster. Post-fire recovery from dNBR severity and NDVI time series.

---

## 1. Overview

Monitors post-fire vegetation dynamics in two steps: burn severity is first classified with dNBR, then recovery trajectories are tracked from multi-temporal post-fire NDVI time series. Suitable for burn-scar loss assessment, vegetation recovery monitoring, and post-disaster ecological restoration planning.

Core algorithms:

- **Burn severity (dNBR)**: normalized burn ratio NBR=(NIR−SWIR)/(NIR+SWIR), differenced dNBR=NBR_pre−NBR_post. Classified into five levels by the USGS / Key et al. 2006 thresholds: unburned (<0.10) / low (0.10–0.27) / moderate_low (0.27–0.44) / moderate_high (0.44–0.66) / high (≥0.66).
- **Recovery slope**: per-pixel linear slope of the post-fire NDVI series; positive values indicate ongoing recovery.
- **Recovery time**: the period index at which NDVI first returns to pre-fire baseline × target (default 0.95); −1 if not recovered within the observation period.
- **Recovery trajectory**: per-period spatially averaged NDVI (optionally restricted to the burned area).

The `--synthetic` mode generates physically consistent scenarios with different burn severities and recovery rates (offline).

## 3. Quick Start

```bash
pip install -r requirements.txt
python geoskill-post-fire-recovery.py --bbox 116 39 117 40 --synthetic --output-dir ./out
```

## 4. CLI Parameters

Run `python <skill>.py --help` for the full list. Common parameters:

| Parameter | Type | Description |
|---|---|---|
| `--bbox` | `float[4]` | WGS84 bounding box `min_lon min_lat max_lon max_lat` |
| `--input` | `path` | Local input file (GeoJSON/GeoTIFF/etc.) |
| `--output-dir` | `path` | Output directory (default `./output`) |
| `--synthetic` | `flag` | Use synthetic data instead of real input |
| `--quiet` | `flag` | Suppress non-essential stdout |

## 5. Input / Output

| File | Format | Description |
|---|---|---|
| `burn_severity.tif` | GeoTIFF (float32) | Severity 0=unburned … 4=high, EPSG:4326 |
| `dnbr.tif` | GeoTIFF (float32) | Differenced burn ratio dNBR |
| `recovery_year.tif` | GeoTIFF (float32) | Recovery time (period index), −1 = not recovered |
| `recovery_slope.tif` | GeoTIFF (float32) | Linear slope of post-fire NDVI |
| `recovery_trajectory.json` | JSON | Per-period NDVI curves, severity area, recovery ratio |
| `output-manifest.json` | JSON | Run manifest (inputs/outputs/QA/software versions) |


## 6. Technical Principle

(see SKILL.md for details)

## 8. License

MIT License. See [`LICENSE`](./LICENSE) for full text.

---

> 中文完整版：[references/SKILL.zh-CN.md](references/SKILL.zh-CN.md)
