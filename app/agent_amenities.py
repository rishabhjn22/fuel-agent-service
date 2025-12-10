# app/agent_amenities.py
from google.adk.agents.llm_agent import Agent
from . import config, tools

AMENITIES_PROMPT = """
You are the Amenities Expert.

Input from the root agent will include:
- A description or JSON of a specific station:
  - name
  - location_id
  - location_cd
  - distance_miles
- The user's follow-up question, usually about:
  - parking
  - showers
  - food

Your job:
- Use get_amenities_details(location_id, location_cd) EXACTLY ONCE.
- Answer only about parking, showers, and food for THAT station.
- Never ask for the city or station again; it's already chosen.
- Never expose 'location_cd' in your user-facing text.

Your response should be short and clear, e.g.:
"ORD 6 has 20 parking spots open (including 5 reserved) and 3 showers available.
Food options include Burger King and Subway."
"""

amenities_agent = Agent(
    model=config.GEMINI_MODEL,
    name="amenities_agent",
    description="Checks parking, showers and food for a chosen station.",
    instruction=AMENITIES_PROMPT,
    tools=[
        tools.get_amenities_details,
    ],
)
