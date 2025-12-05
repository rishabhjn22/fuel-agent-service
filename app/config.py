# config.py
import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RXO_API_KEY = os.getenv("RXO_API_KEY")
RXO_BEARER_TOKEN = os.getenv("RXO_BEARER_TOKEN")

# External Endpoints
AMENITIES_API = os.getenv("AMENITIES_API", "https://apiconnectdev.rxo.com/Xpo.DriverMobile.Apiv2/Amenities")
AMENITIES_INFO_API = os.getenv("AMENITIES_INFO_API", "https://apiconnectdev.rxo.com/Xpo.DriverMobile.Apiv2/taAmenitiesInfo")

# Model Configuration
GEMINI_MODEL = "gemini-2.5-flash" # Or "gemini-1.5-flash"