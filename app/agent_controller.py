# agent_controller.py
import google.generativeai as genai
import time
import config
from tools import search_amenities, get_amenities_details, get_coordinates_from_city

genai.configure(api_key=config.GEMINI_API_KEY)

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are 'FuelFinder', a professional trucking co-pilot.

### 🧠 DECISION LOGIC
1. **Amenities Toggle:**
   - If User wants "Parking", "Showers", or "Food" -> Call `search_amenities(..., amenities_required=True)`.
   - If User just wants "Fuel" or "Cheapest Price" -> Call `search_amenities(..., amenities_required=False)`.
2. **Execution:**
   - If the tool result says "**RECOMMENDED**", you MUST call `get_amenities_details` immediately.

### 🚛 INTELLIGENCE RULES (CRITICAL)
1. **Food:** When detailing a station, you MUST summarize the `food_options` text (e.g. "They have a Burger King and Subway").
2. **Showers:** Report the number of available showers.
3. **Financials:** Always mention the `driver_price` and `savings` if the data is present.
4. **Parking:** Explicitly distinguish between "Free" and "Reserved" spots if the data splits them.

### 🛑 SECURITY & PROTOCOL
1. **NO NAGGING:** Never ask the user for a Location Code.
2. **NO INTERNAL DATA:** Do not share `location_id` or `location_cd`.

### 🗣️ RESPONSE TEMPLATE
"I found [Station Name] [Distance] away.
Price: [Driver Price] (Savings: [Savings])
Parking: [Count] spots open.
Food: [Food List]
Showers: [Count] available.
[Navigate](Maps URL)"
"""

class AgentManager:
    def __init__(self):
        self.sessions = {}
        self.TIMEOUT_SECONDS = 1800 # 30 Minutes
        
        self.model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            tools=[search_amenities, get_amenities_details, get_coordinates_from_city],
            system_instruction=SYSTEM_PROMPT
        )

    def _cleanup_sessions(self, user_id):
        if user_id in self.sessions:
            if (time.time() - self.sessions[user_id]["last_seen"]) > self.TIMEOUT_SECONDS:
                del self.sessions[user_id]

    def get_chat_session(self, user_id: str):
        self._cleanup_sessions(user_id)
        if user_id not in self.sessions:
            print(f"🆕 Creating new session for {user_id}")
            chat = self.model.start_chat(enable_automatic_function_calling=True)
            self.sessions[user_id] = {"chat": chat, "last_seen": time.time()}
        else:
            self.sessions[user_id]["last_seen"] = time.time()
        return self.sessions[user_id]["chat"]

    def reset_session(self, user_id: str):
        if user_id in self.sessions:
            del self.sessions[user_id]
            return True
        return False

    async def process_message(self, user_id: str, user_text: str, user_lat: float, user_lon: float):
        chat = self.get_chat_session(user_id)
        
        context_message = (
            f"User GPS: ({user_lat}, {user_lon})\n"
            f"Query: {user_text}\n"
            f"SYSTEM NOTE: If tool output contains '**RECOMMENDED**', execute that function immediately."
        )
        
        try:
            response = await chat.send_message_async(context_message)
            return response.text
        except Exception as e:
            self.reset_session(user_id)
            return f"System error ({str(e)}). I have reset the session."

agent_manager = AgentManager()