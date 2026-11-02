---
name: geoskill-post-fire-recovery
description: '用 dNBR（NIR/SWIR 差分归一化烧伤比）判定五级烧伤严重度，结合火后多期 NDVI 恢复曲线估算恢复轨迹、恢复斜率与恢复年限，输出严重度 GeoTIFF、恢复轨迹 JSON 与恢复年限栅格。Post-fire recovery from dNBR severity and NDVI time series.'
---

# 火后植被恢复监测 | Post-Fire Recovery

Monitors post-fire vegetation dynamics in two steps: first, dNBR is used to determine burn severity; second, the post-fire multi-temporal NDVI time series is used to track the recovery trajectory. It suits burned-area loss assessment, vegetation recovery monitoring and post-disaster ecological restoration planning.

Core algorithm:

- **Burn severity (dNBR)**: the normalized burn ratio NBR=(NIR−SWIR)/(NIR+SWIR) is differenced as dNBR=NBR_pre−NBR_post. Following the key thresholds of USGS / Key et al. 2006, five severity classes are defined: unburned (<0.10) / low (0.10–0.27) / moderate_low (0.27–0.44) / moderate_high (0.44–0.66) / high (≥0.66).
- **Recovery slope**: per-pixel linear slope of the post-fire NDVI series; positive values indicate ongoing recovery.
- **Recovery year**: the epoch index at which NDVI first returns to the pre-fire baseline × target (default 0.95); pixels not recovered within the observation period are recorded as −1.
- **Recovery trajectory**: spatially averaged NDVI per epoch (optionally restricted to the burned area).

The `--synthetic` mode generates physically consistent scenes with varying burn severity and recovery rates (offline).

## Dependencies / 依赖

```bash
pip install numpy rasterio scipy
```

## Usage / 使用方法

### Basic usage (synthetic data, offline)

```bash
python geoskill-post-fire-recovery.py --bbox 118.0 34.0 119.0 35.0 --synthetic --n-dates 6 --output-dir ./output
```

### Example 1: adjust the recovery target ratio

```bash
python geoskill-post-fire-recovery.py \
    --bbox 118.0 34.0 119.0 35.0 \
    --synthetic --n-dates 6 --recovery-target 0.90 \
    --output-dir ./target90
```

### Example 2: real multi-band imagery

```bash
python geoskill-post-fire-recovery.py \
    --input fire_scene.tif \
    --n-dates 6 \
    --output-dir ./real
```

Input band order: nir_pre / swir_pre / nir_post / swir_post / ndvi_prefire, followed by `n-dates` bands of post-fire NDVI per epoch.

## Output / 输出

| File | Format | Description |
|---|---|---|
| `burn_severity.tif` | GeoTIFF (float32) | Severity 0=unburned … 4=high, EPSG:4326 |
| `dnbr.tif` | GeoTIFF (float32) | Differenced burn ratio dNBR |
| `recovery_year.tif` | GeoTIFF (float32) | Recovery year (epoch index), −1 = not recovered |
| `recovery_slope.tif` | GeoTIFF (float32) | Post-fire NDVI linear slope |
| `recovery_trajectory.json` | JSON | Per-epoch NDVI curve, severity areas, recovery proportion |
| `output-manifest.json` | JSON | Run manifest (inputs/outputs/QA/software versions) |

## Data Source / 数据源 / Source

- **Synthetic mode**: generated locally, no external data sources
- **Real mode**: user-provided pre-fire/post-fire multi-band GeoTIFF (e.g., Landsat / Sentinel-2)

## Privacy / 隐私声明 / Privacy

- Fully offline by default; no network requests are made
- All computation is performed locally; user data is never uploaded

## License / License

MIT

---

> 中文完整版：需要时再读 [references/SKILL.zh-CN.md](references/SKILL.zh-CN.md)，不要默认全量加载。
