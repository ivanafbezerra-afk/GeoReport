# GeoReport | Google Cloud project configuration.
# Set an environment variable named GOOGLE_CLOUD_PROJECT or edit the fallback below.
# Project IDs are not credentials. Never commit OAuth tokens or service-account keys.
import os

EARTH_ENGINE_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "YOUR_EARTH_ENGINE_PROJECT_ID")
