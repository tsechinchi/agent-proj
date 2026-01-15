from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from langchain.agents import create_agent
from pydantic import SecretStr
import os
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from agents.tools.tools import (
    find_flights,
    find_hotels,
    attraction_finder,
    weather_checker,
    generate_pdf_itinerary,
    email_sender,
)

# System prompts for each agent role
prompt_enhance_sys_pmt = (
    "You are a travel request clarification assistant. Your role is to analyze and rewrite user travel requests "
    "into structured, concise briefs that are actionable and specific.\n"
    "\nYour output MUST be exactly 3 bullet points in this format:\n"
    "• Goals: What does the traveler want to accomplish? (e.g., relax, explore culture, adventure)\n"
    "• Constraints: Budget, time, visa requirements, mobility, dietary, etc.\n"
    "• Preferences: Climate preference, accommodation style, pace, group size, etc.\n"
    "\nBe concise, specific, and practical. Do not add commentary or explanations beyond the 3 bullets."
)

travel_agent_sys_pmt = (
    "You are an expert travel itinerary planner with deep knowledge of destinations, logistics, and travel preferences.\n"
    "\nYour task is to create a detailed, feasible itinerary for the specified duration.\n"
    "\nFor each itinerary, include:\n"
    "1. Flight options: arrival/departure times, approximate costs, direct vs. connecting\n"
    "2. Accommodation suggestions: 2-3 options per night with different budgets\n"
    "3. Daily activities: time-blocked schedule with attractions, dining, transport\n"
    "4. Weather expectations: conditions and what to pack\n"
    "5. Budget summary: estimated total for flights, hotels, food, activities\n"
    "\nIf specific dates or cities are missing, use reasonable placeholders and explicitly state them (e.g., 'Assuming summer 2025').\n"
    "Be practical: account for transit times, rest days, and realistic daily costs. Prioritize value and experiences."
)

detail_plan_sys_pmt = (
    "You are a travel research specialist with access to real-time data on attractions, weather, and local recommendations.\n"
    "\nYour role is to provide detailed, curated insights for travel planning:\n"
    "\n1. Attractions & Activities: Research museums, parks, restaurants, festivals, cultural sites, adventure activities.\n"
    "   - Include opening hours, cost, booking links if available\n"
    "   - Prioritize based on traveler interests (e.g., museums, food, nature, nightlife)\n"
    "2. Weather & Conditions: Fetch detailed forecasts for travel dates.\n"
    "   - Highlight extreme weather, seasonal challenges, best times to visit\n"
    "3. Local Tips: Transportation, safety, cultural etiquette, currency, best neighborhoods.\n"
    "4. Visa & Documentation: Any entry requirements or travel advisories.\n"
    "\nUse available tools to fetch real data. Present information in a concise, actionable format."
)

util_sys_pmt = (
    "You are a travel logistics coordinator responsible for finalizing and delivering itineraries.\n"
    "\nYour responsibilities:\n"
    "1. PDF Generation: Format the final itinerary into a professional, printable PDF with:\n"
    "   - Cover page (destination, dates, traveler name if provided)\n"
    "   - Day-by-day schedule\n"
    "   - Flight & hotel bookings\n"
    "   - Maps and contact info\n"
    "2. Email Delivery: Send the itinerary to the traveler's email with a personalized message.\n"
    "3. User Approval: Always ask for explicit user confirmation before generating or sending anything.\n"
    "\nBe professional, thorough, and user-focused. Ensure all critical details are included."
)

class MockLLM:
    """Offline placeholder when OPENAI_API_KEY is missing."""

    def invoke(self, messages, **kwargs):
        return type('MockResponse', (), {'content': "Mock response: LLM key missing (offline mode)."})()


def build_llm():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set; using MockLLM (offline mode).")
        return MockLLM()
    return ChatOpenAI(
        model="nvidia/nemotron-3-nano-30b-a3b:free",
        base_url="https://openrouter.io/api/v1",
        api_key=SecretStr(api_key),
        temperature=0,
    )


# Initialize models (used directly in stategraph.py; no agent wrapper classes needed)
prompt_enhance_model = build_llm()
accom_flight_model = build_llm()
detail_plan_model = build_llm()
util_model = build_llm()






