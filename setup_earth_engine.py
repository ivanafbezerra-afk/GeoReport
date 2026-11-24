# -*- coding: utf-8 -*-
"""Authorize Google Earth Engine once before using GeoReport remotely.

Run this script from Spyder after installing earthengine-api. Never publish
OAuth authorization codes, service-account keys or user access tokens.
"""
import ee
from earth_engine_config import EARTH_ENGINE_PROJECT

if EARTH_ENGINE_PROJECT == "YOUR_EARTH_ENGINE_PROJECT_ID":
    raise ValueError(
        "Configure EARTH_ENGINE_PROJECT in earth_engine_config.py "
        "or set the GOOGLE_CLOUD_PROJECT environment variable."
    )

# The localhost authentication flow usually opens a browser on Windows.
ee.Authenticate(auth_mode="localhost")
ee.Initialize(project=EARTH_ENGINE_PROJECT)
asset_id = (
    "projects/mapbiomas-public/assets/brazil/lulc_10m/collection4/"
    "mapbiomas_10m_collection4_coverage_v1"
)
collection = ee.Image(asset_id)
print("Earth Engine connected. Latest bands:", collection.bandNames().getInfo()[-3:])
print("2025 classification available:",
      collection.bandNames().contains("classification_2025").getInfo())
