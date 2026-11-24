# GeoReport — Automated Territorial Diagnostics

**Python / GeoPandas / Rasterio / Google Earth Engine / MapBiomas / ReportLab**

GeoReport validates polygon datasets, identifies Brazilian states using the IBGE 2024 boundaries,
obtains MapBiomas Collection 4 land-cover classifications for 2025, computes area statistics,
and exports English thematic maps and five-page technical PDF reports.

## How to run

1. Create a Conda environment (Windows/Spyder): `conda install -c conda-forge geopandas rasterio matplotlib numpy pandas shapely reportlab earthengine-api google-api-python-client`.
2. Configure your Google Cloud project ID in `earth_engine_config.py` or set the `GOOGLE_CLOUD_PROJECT` environment variable. You need an Earth Engine-enabled project and authenticated account for remote downloads.
3. Run `setup_earth_engine.py` once to authorize Earth Engine.
4. Open `main.py` in Spyder and press **F5**. Choose **1** for the Federal District or **2** to select a SHP, GPKG or GeoJSON in Brazil.
5. If a compatible local MapBiomas GeoTIFF exists in `data/processed` or `data/rasters`, GeoReport uses it. Otherwise, it requests the raster via Earth Engine. Large exports may be resumed through Google Drive.

## Main scripts

| Script | Purpose |
| --- | --- |
| `main.py` | Study-area selection, validation, raster analysis, map generation and orchestration |
| `earth_engine_mapbiomas.py` | MapBiomas access and Earth Engine download/export handling |
| `google_drive_export.py` | Drive export tracking, tile download and raster mosaics |
| `technical_report.py` | Five-page English technical PDF |
| `earth_engine_config.py` | Cloud project ID configuration (no credentials committed) |
| `setup_earth_engine.py` | Initial Earth Engine authorization |
| `test_earth_engine_download.py` / `test_google_drive.py` | Optional connectivity checks |

## Output files

Each completed run produces the following English-language products in `outputs/maps/` or `outputs/study_areas/<area-name>/`:

- `land_cover_map.png` and `land_cover_map.pdf`: thematic cartography with fixed coordinate frame, state inset, scale bar and class legend
- `territorial_diagnostics_report.pdf`: five-page report with quantitative table, chart and methods
- `land_cover_statistics.csv`: area by MapBiomas class (English class names)
- `clipped_land_cover.tif`: classification raster clipped to the selected polygon
- `processed_study_area.gpkg`: projected vector dataset

Raster processing occurs **only once per run**. The map and report use the same statistics.
The full workspace package includes a Federal District raster and official IBGE/state and sample boundary files for an offline test. The public GitHub package omits large input data. Download the 2024 IBGE state boundaries to `data/input/` and supply a compatible MapBiomas GeoTIFF, or configure Earth Engine.

## Methodological notes

The 2025 MapBiomas classification is a categorical land-cover snapshot, **not a temporal NDVI-change analysis**. Areas are estimated from classified pixels; edge effects and reprojection can lead to small differences from vector areas. UTM projection is suitable for local and regional analyses; nationwide geometries require additional area-preserving methodology. Accuracy depends on the MapBiomas source product and is not independently validated in this software.

**Project author:** Ivana Bezerra. **Data sources:** IBGE administrative boundaries (2024), MapBiomas land-cover Collection 4 (2025). This repository is intended for portfolio demonstration.

## Demonstration outputs

The `examples/` directory contains an English land-cover map and a five-page technical report generated from the FCTE/UnB test polygon. The example files are not required for execution.

## Privacy and publication

Before committing to GitHub, verify that no credentials, private GIS datasets, cached export task files or large raster downloads are tracked. `.gitignore` excludes those locations; this public source package intentionally contains only the code, documentation, north-arrow asset and portfolio examples.
