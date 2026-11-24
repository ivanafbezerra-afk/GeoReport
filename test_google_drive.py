# -*- coding: utf-8 -*-
"""Read-only Google Drive API connectivity check for GeoReport."""
import ee
from earth_engine_config import EARTH_ENGINE_PROJECT
from google_drive_export import connect_drive

if EARTH_ENGINE_PROJECT == "YOUR_EARTH_ENGINE_PROJECT_ID":
    raise ValueError("Configure your Google Cloud project in earth_engine_config.py.")

ee.Initialize(project=EARTH_ENGINE_PROJECT)
service = connect_drive()
results = service.files().list(
    q="trashed = false and name contains 'GeoReport_MapBiomas_'",
    fields="nextPageToken,files(id,name,createdTime)",
    pageSize=10,
).execute()
print("Google Drive API connection succeeded.")
print("GeoReport export files found:", len(results.get("files", [])))
for file_info in results.get("files", []):
    print("-", file_info["name"])
print("No Drive files were changed or deleted.")
