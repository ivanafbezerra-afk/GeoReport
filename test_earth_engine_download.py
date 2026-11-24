# -*- coding: utf-8 -*-
"""Optional Google Earth Engine download test for a small polygon.

Select a study area, such as the UnB FCTE campus, to force a GEE request
regardless of any matching raster in the local cache.
"""
from pathlib import Path
from tkinter import Tk, filedialog
import geopandas as gpd
from earth_engine_config import EARTH_ENGINE_PROJECT
from earth_engine_mapbiomas import download_mapbiomas_raster, PendingDriveExport


def main():
    """Select an area and test direct Earth Engine raster retrieval."""
    project_dir = Path(__file__).resolve().parent
    window = Tk()
    window.withdraw()
    window.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            title="Select a small study area to test Earth Engine",
            filetypes=[("Vector datasets", "*.shp *.gpkg *.geojson")],
        )
    finally:
        window.destroy()
    if not selected:
        print("Test canceled: no area selected.")
        return
    study_area = gpd.read_file(selected)
    if study_area.empty or study_area.crs is None:
        raise ValueError("The study area is empty or has no defined CRS.")
    try:
        raster_path = download_mapbiomas_raster(
            area=study_area,
            output_dir=project_dir / "data" / "rasters" / "earth_engine_cache" / "2025",
            earth_engine_project=EARTH_ENGINE_PROJECT,
            year=2025,
        )
        print("SUCCESS: GeoTIFF downloaded to:", raster_path)
    except PendingDriveExport as pending:
        print("Large export was submitted to Google Drive:")
        print(pending)


if __name__ == "__main__":
    main()
