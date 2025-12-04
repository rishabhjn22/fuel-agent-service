# backend/app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

AMENITIES_API = os.getenv("AMENITIES_API", "https://apiconnectdev.rxo.com/Xpo.DriverMobile.Apiv2/Amenities")
AMENITIES_INFO_API = os.getenv("AMENITIES_INFO_API", "https://apiconnectdev.rxo.com/Xpo.DriverMobile.Apiv2/taAmenitiesInfo")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
