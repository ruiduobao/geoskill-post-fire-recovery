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
