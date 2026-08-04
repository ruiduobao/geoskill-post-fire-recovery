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

## 2. Features

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

## 7. Methodology

This skill has been methodologically reviewed. See [`REVIEW.md`](./REVIEW.md) for:

- P0/P1/P2 issue counts and verdicts
- Reproduction commands
- Known limitations and edge cases

## 8. License

MIT License. See [`LICENSE`](./LICENSE) for full text.

---

# 火后植被恢复监测（中文版）

> 本部分为完整中文文档，与上方英文部分对应。

---
name: geoskill-post-fire-recovery
description: '用 dNBR（NIR/SWIR 差分归一化烧伤比）判定五级烧伤严重度，结合火后多期 NDVI 恢复曲线估算恢复轨迹、恢复斜率与恢复年限，输出严重度 GeoTIFF、恢复轨迹 JSON 与恢复年限栅格。Post-fire recovery from dNBR severity and NDVI time series.'
---

# 火后植被恢复监测 | Post-Fire Recovery

分两步监测火灾后的植被动态：先用 dNBR 判定烧伤严重度，再用火后多期 NDVI
时间序列追踪恢复轨迹。适用于过火区损失评估、植被恢复监测与灾后生态恢复规划。

核心算法：

- **烧伤严重度（dNBR）**：归一化烧伤比 NBR=(NIR−SWIR)/(NIR+SWIR)，
  差分 dNBR=NBR_pre−NBR_post。按 USGS / Key et al. 2006 关键阈值分为五级：
  unburned (<0.10) / low (0.10–0.27) / moderate_low (0.27–0.44) /
  moderate_high (0.44–0.66) / high (≥0.66)。
- **恢复斜率**：火后 NDVI 序列的每像元线性斜率，正值表示恢复中。
- **恢复年限**：NDVI 首次回到火前基线 × target（默认 0.95）的期号；观测期内
  未恢复记 −1。
- **恢复轨迹**：逐期空间平均 NDVI（可限定在过火区内）。

支持 `--synthetic` 模式生成含不同烧伤严重度与恢复速率的物理一致场景（离线）。

## 依赖

```bash
pip install numpy rasterio scipy
```

## 使用方法

### 基本用法（合成数据，离线）

```bash
python geoskill-post-fire-recovery.py --bbox 118.0 34.0 119.0 35.0 --synthetic --n-dates 6 --output-dir ./output
```

### 示例 1：调整恢复目标比例

```bash
python geoskill-post-fire-recovery.py \
    --bbox 118.0 34.0 119.0 35.0 \
    --synthetic --n-dates 6 --recovery-target 0.90 \
    --output-dir ./target90
```

### 示例 2：真实多波段影像

```bash
python geoskill-post-fire-recovery.py \
    --input fire_scene.tif \
    --n-dates 6 \
    --output-dir ./real
```

输入波段顺序：nir_pre / swir_pre / nir_post / swir_post / ndvi_prefire，其后
`n-dates` 个波段为火后各期 NDVI。

## 输出

| 文件 | 格式 | 说明 |
|---|---|---|
| `burn_severity.tif` | GeoTIFF (float32) | 严重度 0=unburned … 4=high，EPSG:4326 |
| `dnbr.tif` | GeoTIFF (float32) | 差分烧伤比 dNBR |
| `recovery_year.tif` | GeoTIFF (float32) | 恢复年限（期号），−1=未恢复 |
| `recovery_slope.tif` | GeoTIFF (float32) | 火后 NDVI 线性斜率 |
| `recovery_trajectory.json` | JSON | 逐期 NDVI 曲线、严重度面积、恢复比例 |
| `output-manifest.json` | JSON | 运行清单（输入/输出/QA/软件版本） |

## 数据源 / Source

- **合成模式**：本地生成，无外部数据源
- **真实模式**：用户提供火前/火后多波段 GeoTIFF（如 Landsat / Sentinel-2）

## 隐私声明 / Privacy

- 默认完全离线运行，不发起任何网络请求
- 所有计算在本地完成，不上传用户数据

## License

MIT
