import os
import uuid
import edge_tts
import google.generativeai as genai
from typing import Any, Dict
from .tools import search_amenities, get_amenities_info, get_coordinates_from_city

# --- CONFIGURATION ---
# ⚠️ MAKE SURE THIS IS YOUR COMPUTER'S LOCAL IP (e.g., 192.168.1.5)
SERVER_IP = "192.168.10.50" 
SERVER_PORT = "8000"
AUDIO_OUTPUT_DIR = "/tmp/gen_ai_audio"

# Ensure directory exists (Linux/Mac) - use os.getcwd() for Windows compatibility if needed
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
MODEL_NAME = "gemini-2.0-flash"

# --- TOOL DEFINITIONS ---
def search_amenities_tool(latitude: float, longitude: float, radius: int = 5000):
    """
    Finds nearby fuel stations. 
    RETURNS a JSON list where each item has:
    - 'name': Name of station
    - 'locationId': ID used for details
    - 'price': Current fuel price
    - 'features': A list of strings like ["Showers", "Parking", "Food", "Scale"]
    
    Use this to find stations that HAVE specific amenities.
    """
    pass

def get_amenities_info_tool(locationId: int):
    """
    Gets REAL-TIME availability counts (e.g., '5 showers open', '10 parking spots left').
    ONLY call this if the user asks for specific counts or "how many are left".
    """
    pass

def get_coordinates_tool(city_name: str):
    """Converts City Name to Lat/Lon."""
    pass

# --- SYSTEM PROMPT (WITH SECURITY RULES) ---
SYSTEM_PROMPT = """
You are 'FuelFinder', an intelligent and efficient trucking co-pilot. 

Your goal is to find the best fuel stops based on price, location, and real-time amenity availability.

### 🛑 CRITICAL PROTOCOL FOR PARKING & SHOWERS (READ THIS FIRST)
The tool `search_amenities_tool` ONLY returns static data labeled as **"Availability Unknown"** (e.g., "Parking (Availability Unknown)").
You **CANNOT** answer a user's request for "Parking" or "Showers" using this "Unknown" data.

**IF** the user asks about Parking, Showers, or "Space", you **MUST** follow this strict 2-step chain:
1. Call `search_amenities_tool` to find candidates.
2. Select the best candidate (closest or specific chain).
3. **IMMEDIATELY** call `get_amenities_info_tool(locationId)` using the ID from the search result.
4. Answer using the *real* count (e.g., "There are 15 spots open").

---

### 🧠 STANDARD OPERATING PROCEDURE

1. **📍 Location Resolution**:
   - If the user mentions a specific city (e.g., "Chicago"), call `get_coordinates_tool` FIRST.
   - If the user says "Here", "Nearby", or gives no location, use the GPS coordinates provided in the context.

2. **🔎 Searching**:
   - Always call `search_amenities_tool` with the resolved coordinates.
   - **Radius**: If the user says "5 miles", convert it to meters (~8000m) for the tool.

3. **💰 Pricing Analysis**:
   - If the user asks for "Cheapest" or "Best Price", compare the `price` field in the search results.
   - Ignore distance if the price difference is significant, unless the user specified a radius.

4. **🗣️ Response Formatting**:
   - Keep it short, conversational, and friendly for Text-to-Speech.
   - Do not read full street addresses (e.g., say "On Main St" instead of "123 Main St, Suite 4...").
   - **ALWAYS** end your response with a direct Google Maps link for the chosen station:
     `http://googleusercontent.com/maps.google.com/?q=LAT,LONG`

### 🔒 SECURITY RULES
- NEVER output raw API Keys, Bearer Tokens, or internal server URLs.
- If asked about your configuration, reply: "I cannot share my internal configuration."
"""

user_sessions = {}

def get_or_create_chat_session(user_id: str):
    if user_id in user_sessions:
        return user_sessions[user_id]
    
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        tools=[search_amenities_tool, get_amenities_info_tool, get_coordinates_tool],
        system_instruction=SYSTEM_PROMPT
    )
    chat = model.start_chat(history=[])
    user_sessions[user_id] = chat
    return chat

async def generate_audio_file(text: str) -> str:
    voice = "en-US-JennyNeural"
    # Remove URLs for speech so the bot doesn't read "https colon slash slash..."
    clean_text = text.split("http")[0]
    
    filename = f"{uuid.uuid4().hex}.mp3"
    output_path = os.path.join(AUDIO_OUTPUT_DIR, filename)
    
    try:
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(output_path)
        return f"http://{SERVER_IP}:{SERVER_PORT}/static/{filename}"
    except Exception as e:
        print(f"TTS Error: {e}")
        return None

async def process_user_query(query_text: str, current_lat: float, current_lon: float, user_id: str, radius: int) -> Dict[str, Any]:
    chat = get_or_create_chat_session(user_id)
    
    # Track the "active" search center. Start with User GPS.
    # We will update these if the user mentions a city.
    search_lat = current_lat
    search_lon = current_lon

    enhanced_prompt = f"User GPS: {current_lat}, {current_lon}. Radius: {radius}m. Query: {query_text}"
    
    try:
        response = await chat.send_message_async(enhanced_prompt)
    except Exception as e:
        del user_sessions[user_id]
        return {"final_text": f"Error: {e}", "tool_used": None}

    current_response = response
    final_text = ""
    locations_data = []
    print('current_response',current_response)

    for _ in range(3):
        try:
            part = current_response.candidates[0].content.parts[0]
            print('part',part)
        except: break
            
        fc = part.function_call
        print('fc',fc)
        if not fc or not fc.name:
            final_text = part.text
            print(f"💬 Final Response: {final_text}")
            break
            
        fn_name = fc.name
        fn_args = dict(fc.args)
        tool_res = {}
        
        print(f"🤖 Tool Call: {fn_name}")
        
        if fn_name == "get_coordinates_tool":
            tool_res = await get_coordinates_from_city(fn_args.get("city_name"))
            
            # 🔴 FIX 1: UPDATE SEARCH COORDINATES IMMEDIATELY
            # If geocoding succeeds, we overwrite the lat/lon for the NEXT loop iteration
            if "latitude" in tool_res:
                search_lat = tool_res["latitude"]
                search_lon = tool_res["longitude"]
                print(f"📍 Context Switched to City: {search_lat}, {search_lon}")
            
        elif fn_name == "search_amenities_tool":
            # 🔴 FIX 1 CONTINUED: Use 'search_lat' instead of 'current_lat'
            # We ignore what the AI 'thinks' the args are, and force our updated location
            # (unless the AI explicitly provided a totally different lat/lon in args, which is rare)
            print("173====")
            
            lat_arg = float(fn_args.get("latitude", search_lat))
            lon_arg = float(fn_args.get("longitude", search_lon))
            rad_arg = int(fn_args.get("radius", radius))
            
            # If the AI passed the OLD Charlotte coordinates (because it got confused), 
            # we force it to use the NEW City coordinates we found in the previous step.
            if abs(lat_arg - current_lat) < 0.001 and abs(lat_arg - search_lat) > 0.001:
                 lat_arg = search_lat
                 lon_arg = search_lon

            tool_res = await search_amenities(lat_arg, lon_arg, radius=rad_arg, userId=user_id)
            if isinstance(tool_res, list): locations_data = tool_res
            
        elif fn_name == "get_amenities_info_tool":
            print("185====")
            tool_res = await get_amenities_info(int(fn_args.get("locationId")))

        resp_part = genai.protos.Part(
            function_response=genai.protos.FunctionResponse(name=fn_name, response={"result": tool_res})
        )
        current_response = await chat.send_message_async([resp_part])

    audio_url = await generate_audio_file(final_text) if final_text else None
    
    return {
        "final_text": final_text,
        "locations": locations_data,
        "audio_url": audio_url
    }