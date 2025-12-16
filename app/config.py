# config.py
import os
from dotenv import load_dotenv

# 1) Load variables from .env file into environment
load_dotenv()

# 2) Your existing config values
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RXO_API_KEY = os.getenv("RXO_API_KEY")
RXO_BEARER_TOKEN = os.getenv("RXO_BEARER_TOKEN")

AMENITIES_API = os.getenv(
    "AMENITIES_API",
    "https://apiconnectdev.rxo.com/Xpo.DriverMobile.Apiv2/Amenities",
)
AMENITIES_INFO_API = os.getenv(
    "AMENITIES_INFO_API",
    "https://apiconnectdev.rxo.com/Xpo.DriverMobile.Apiv2/taAmenitiesInfo",
)

# 3) Model name we’ll use with ADK
GEMINI_MODEL = "gemini-2.5-flash-lite"

# 4) Make sure ADK / google.genai see GOOGLE_API_KEY
#    If GOOGLE_API_KEY is not set but GEMINI_API_KEY is, copy it over.
if GEMINI_API_KEY and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

# Token URL (where we POST to get access token)
TOKEN_URL = os.getenv("TOKEN_URL")

# Body fields (all come from .env)
TOKEN_CLIENT_ID = os.getenv("TOKEN_CLIENT_ID")
TOKEN_CLIENT_SECRET = os.getenv("TOKEN_CLIENT_SECRET")
TOKEN_SCOPE = os.getenv("TOKEN_SCOPE")
TOKEN_GRANT_TYPE = os.getenv("TOKEN_GRANT_TYPE", "client_credentials")

# Header API key for token call (x-api-key)
TOKEN_X_API_KEY = os.getenv("TOKEN_X_API_KEY")