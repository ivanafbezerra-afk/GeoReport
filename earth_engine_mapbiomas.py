# -*- coding: utf-8 -*-
"""GeoReport | Fetch MapBiomas land-cover rasters using Google Earth Engine."""

from pathlib import Path
import math
import re
import hashlib
from urllib.request import urlopen

from google_drive_export import register_export_task, complete_drive_export

import geopandas as gpd
from shapely.geometry import box, mapping

ASSET_MAPBIOMAS_10M_C4 = (
    "projects/mapbiomas-public/assets/brazil/lulc_10m/collection4/"
    "mapbiomas_10m_collection4_coverage_v1"
)

FIRST_AVAILABLE_YEAR = 2017
LAST_AVAILABLE_YEAR = 2025
RESOLUTION_METERS = 10
# Keep a safe margin below the API size limits.
MAX_DIRECT_DOWNLOAD_PIXELS = 3_000_000
# Maximum estimated pixel count at 10 m; larger areas need a special workflow.
# Split large Drive exports into 4096-pixel tiles.
MAX_DRIVE_EXPORT_PIXELS = 2_000_000_000
DRIVE_TILE_SIZE = 4096


class PendingDriveExport(RuntimeError):
    """Pendingdriveexport."""


def initialize_earth_engine(earth_engine_project):
    """Initialize the Earth Engine API using configured Cloud project."""
    if not earth_engine_project or not earth_engine_project.strip():
        raise ValueError(
            "Set the Google Cloud project ID in EARTH_ENGINE_PROJECT in "
            "main.py before using Earth Engine."
        )
    try:
        import ee
    except ImportError as exc:
        raise ImportError(
            "Earth Engine is not installed in this Python environment. Install "
            "earthengine-api in the Spyder environment."
        ) from exc

    try:
        ee.Initialize(project=earth_engine_project.strip())
    except Exception as exc:
        raise RuntimeError(
            "Failed to initialize Earth Engine. First run "
            "setup_earth_engine.py with a registered and enabled Cloud project. "
            f"Details: {exc}"
        ) from exc
    return ee


def _geojson_union(gdf_4326):
    """Geojson union."""
    return mapping(gdf_4326.geometry.union_all())


def download_mapbiomas_raster(
    area,
    output_dir,
    earth_engine_project,
    year=2025,
    direct_pixel_limit=MAX_DIRECT_DOWNLOAD_PIXELS,
):
    """Retrieve a MapBiomas GeoTIFF for an area using Earth Engine."""
    if year not in range(FIRST_AVAILABLE_YEAR, LAST_AVAILABLE_YEAR + 1):
        raise ValueError(f"MapBiomas Collection 4 (10 m) covers {FIRST_AVAILABLE_YEAR}–{LAST_AVAILABLE_YEAR}.")
    if area.empty or area.crs is None:
        raise ValueError("The study area must contain features and have a defined CRS.")
    if not area.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("Earth Engine requires polygon features as the study area.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Use a geometry-based cache key to avoid reusing the wrong raster.
    chave_area = hashlib.sha256(
        area.to_crs(4326).geometry.union_all().wkb
    ).hexdigest()[:12]
    destino = output_dir / f"mapbiomas_earth_engine_c4_{year}_{chave_area}.tif"
    state_file = output_dir / f"earth_engine_export_c4_{year}_{chave_area}.json"
    if destino.is_file() and destino.stat().st_size > 0:
        print("Using cached raster:", destino)
        return destino

    # UTM is appropriate for local metric analysis. For large regions,
    # consider regional equal-area projections and tiled processing.
    crs_utm = area.estimate_utm_crs()
    if crs_utm is None:
        raise ValueError("Could not estimate a UTM CRS for the study area.")
    area_utm = area.to_crs(crs_utm)
    xmin, ymin, xmax, ymax = area_utm.total_bounds

    # Pad the export request by 20 m so that rounding does not drop
    # boundary cells from the requested Earth Engine grid.
    xmin, ymin, xmax, ymax = (
        xmin - 2 * RESOLUTION_METERS,
        ymin - 2 * RESOLUTION_METERS,
        xmax + 2 * RESOLUTION_METERS,
        ymax + 2 * RESOLUTION_METERS,
    )
    nx = math.ceil((xmax - xmin) / RESOLUTION_METERS)
    ny = math.ceil((ymax - ymin) / RESOLUTION_METERS)
    pixels_estimados = nx * ny
    print(f"Grade aproximada: {nx} x {ny} = {pixels_estimados:,} pixels")
    print("Download projection:", crs_utm.to_string())
    if pixels_estimados > MAX_DRIVE_EXPORT_PIXELS:
        raise ValueError(
            f"A area requer cerca de {pixels_estimados:,} pixels a 10 m. "
            "The requested area exceeds the default limit. Use tiled regional export."
        )

    # Use the original AOI as the thematic mask and a padded export extent.
    geom_area = _geojson_union(area.to_crs(4326))
    envelope_utm = gpd.GeoSeries(
        [box(xmin, ymin, xmax, ymax)], crs=crs_utm
    ).to_crs(4326)
    geom_envelope = mapping(envelope_utm.iloc[0])

    ee = initialize_earth_engine(earth_engine_project)

    # Resume existing pending tasks instead of creating duplicate exports.
    if state_file.exists():
        print("Resuming previous Earth Engine export:", state_file.name)
        pronto = complete_drive_export(
            ee, state_file, destino, espera_max_s=600
        )
        if pronto is not None:
            return pronto
        raise PendingDriveExport(
            "Earth Engine export still in progress or awaiting Drive delivery. "
            "Task ID has been saved; rerun GeoReport to resume the same export."
        )

    ee_area = ee.Geometry(geom_area)
    ee_envelope = ee.Geometry(geom_envelope)
    imagem = (
        ee.Image(ASSET_MAPBIOMAS_10M_C4)
        .select(f"classification_{year}")
        .clip(ee_area)
        .unmask(0)
        .toUint8()
    )

    if (
        pixels_estimados <= direct_pixel_limit
        and max(nx, ny) <= 9_000
    ):
        print("Downloading GeoTIFF directly from Earth Engine...")
        try:
            url = imagem.getDownloadURL({
                "region": ee_envelope,
                "crs": crs_utm.to_string(),
                "scale": RESOLUTION_METERS,
                "format": "GEO_TIFF",
            })
            parcial = destino.with_suffix(".parcial.tif")
            with urlopen(url, timeout=240) as origem, parcial.open("wb") as saida:
                while True:
                    bloco = origem.read(1024 * 1024)
                    if not bloco:
                        break
                    saida.write(bloco)
            if parcial.stat().st_size == 0:
                raise RuntimeError("Earth Engine returned an empty raster.")
            # Failed downloads must never leave an incomplete final GeoTIFF.
            parcial.replace(destino)
        except Exception as exc:
            parcial = destino.with_suffix(".parcial.tif")
            parcial.unlink(missing_ok=True)
            raise RuntimeError(
                "Direct Earth Engine download failed. "
                "Check your internet connection, authorization and request size. "
                f"Details: {exc}"
            ) from exc

        # Check that the downloaded file is a readable GeoTIFF.
        import rasterio
        try:
            with rasterio.open(destino) as src:
                if src.count != 1 or src.crs is None:
                    raise ValueError("The downloaded GeoTIFF must have a CRS and a single band.")
                print("Earth Engine raster saved:", destino)
                print("CRS:", src.crs, "| Dimensions:", src.width, "x", src.height)
        except Exception:
            destino.unlink(missing_ok=True)
            raise
        return destino

    # For large areas, export to Drive and download through the Drive API.
    # Save pending export metadata so the task can be resumed.
    descricao = re.sub(
        r"[^A-Za-z0-9_-]", "_", f"GeoReport_MapBiomas_{year}_{chave_area}"
    )
    try:
        tarefa = ee.batch.Export.image.toDrive(
            image=imagem,
            description=descricao,
            folder="GeoReport",
            fileNamePrefix=descricao,
            region=ee_envelope,
            scale=RESOLUTION_METERS,
            crs=crs_utm.to_string(),
            fileFormat="GeoTIFF",
            maxPixels=1e13,
            fileDimensions=DRIVE_TILE_SIZE,
            shardSize=256,
            skipEmptyTiles=False,
        )
        tarefa.start()
        register_export_task(
            state_file, tarefa.id, descricao, drive_folder="GeoReport",
            expected_file_count=(
                math.ceil(nx / DRIVE_TILE_SIZE)
                * math.ceil(ny / DRIVE_TILE_SIZE)
            ),
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not create the Earth Engine Drive export task: {exc}"
        ) from exc

    print(f"Export started: ID={tarefa.id}, prefix={descricao}")
    print("Earth Engine may split this export into multiple GeoTIFF tiles (4096 by 4096 pixels).")
    print("GeoReport will track the task and automatically mosaic the resulting GeoTIFF files.")
    pronto = complete_drive_export(
        ee, state_file, destino, espera_max_s=600
    )
    if pronto is not None:
        return pronto
    raise PendingDriveExport(
        f"Pending Earth Engine export: ID={tarefa.id}. "
        "The task is still active in Earth Engine, and its ID was saved locally. "
        "Rerun GeoReport to resume it without launching a duplicate task."
    )
