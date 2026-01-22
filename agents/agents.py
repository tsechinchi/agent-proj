"""Agent builders for the travel planner system.

Three agent types:
1. Planner: Creates itineraries and handles user clarification
2. Refiner: Enhances plans with tool data
3. ToolSelector: Autonomously decides which tools to invoke

Mock mode is supported when OPENAI_API_KEY is not set - all agents return
sensible mock responses that allow the full graph to execute for testing.
"""

from langchain_openai import ChatOpenAI
from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import SecretStr
import os
import logging
import json
import re
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from agents.tools.tools import (
    find_flights,
    find_hotels,
    attraction_finder,
    weather_checker,
)

# Check if we're in mock mode
MOCK_MODE = not os.getenv("OPENAI_API_KEY")
if MOCK_MODE:
    logger.info("🤖 Running in MOCK MODE - LLM calls will return simulated responses")


class MockLLM:
    """Intelligent mock LLM for offline testing.
    
    Produces context-aware responses based on the input prompt,
    allowing the full graph to execute without API calls.
    """

    def invoke(self, messages, **kwargs):
        """Analyze input and return contextual mock response."""
        # Extract the last message content for context
        content = ""
        if isinstance(messages, list) and messages:
            last_msg = messages[-1]
            if hasattr(last_msg, 'content'):
                content = last_msg.content
            elif isinstance(last_msg, str):
                content = last_msg
        elif isinstance(messages, str):
            content = messages
        
        # Generate contextual response based on prompt type
        response_text = self._generate_contextual_response(content.lower())
        
        return type('MockResponse', (), {'content': response_text})()
    
    def _generate_contextual_response(self, content: str) -> str:
        """Generate response based on detected prompt type."""
        
        # Tool selection prompts
        if "decide which tools" in content or "available tools" in content:
            tools = []
            if "flights" in content and "yes" in content.split("flights")[1][:50].lower():
                tools.append("find_flights")
            if "hotels" in content and "yes" in content.split("hotels")[1][:50].lower():
                tools.append("find_hotels")
            if "attractions" in content and "yes" in content.split("attractions")[1][:50].lower():
                tools.append("attraction_finder")
            if "weather" in content and "yes" in content.split("weather")[1][:50].lower():
                tools.append("weather_checker")
            # Default to attractions and weather if destination is mentioned
            if not tools and ("destination" in content or "paris" in content or "tokyo" in content):
                tools = ["attraction_finder", "weather_checker"]
            return f"Based on the available data, I'll call these tools: {json.dumps(tools)}"
        
        # Clarification/enhancement prompts
        if "clarify" in content or "enhance" in content or "goals" in content:
            return (
                "**Clarified Travel Request (Mock)**\n\n"
                "• **Goals**: Experience local culture, visit major landmarks, enjoy local cuisine\n"
                "• **Constraints**: Standard budget, flexible timing, no visa requirements\n"
                "• **Preferences**: Mix of relaxation and exploration, comfortable accommodations"
            )
        
        # Draft plan prompts
        if "itinerary" in content or "day-by-day" in content or "outline" in content:
            # Extract duration if mentioned
            duration = 3
            for word in content.split():
                if word.isdigit():
                    duration = int(word)
                    break
            
            days = []
            for day in range(1, duration + 1):
                if day == 1:
                    days.append(f"**Day {day}: Arrival & Orientation**\n  - Arrive and settle in\n  - Evening walk to explore neighborhood\n  - Welcome dinner at local restaurant")
                elif day == duration:
                    days.append(f"**Day {day}: Departure**\n  - Morning leisure time\n  - Last-minute shopping\n  - Depart for home")
                else:
                    days.append(f"**Day {day}: Exploration**\n  - Morning: Visit major attractions\n  - Afternoon: Cultural experiences\n  - Evening: Local dining")
            
            return "**Draft Itinerary (Mock)**\n\n" + "\n\n".join(days)
        
        # Refinement prompts (with tool data)
        if "enhance" in content or "refine" in content or "real data" in content:
            return (
                "**Refined Itinerary (Mock - with tool data)**\n\n"
                "**Day 1: Arrival**\n"
                "- ✈️ Arrive via recommended flight options (see flight data below)\n"
                "- 🏨 Check into hotel (see accommodation options)\n"
                "- 🌤️ Weather looks favorable for evening walk\n"
                "- 🍽️ Dinner at local restaurant\n\n"
                "**Day 2: Exploration**\n"
                "- 🎭 Visit top attractions (see attraction data)\n"
                "- 🍜 Lunch at popular local spot\n"
                "- 🌆 Afternoon cultural experience\n\n"
                "**Day 3: Departure**\n"
                "- ☕ Leisurely morning\n"
                "- 🛍️ Last-minute shopping\n"
                "- ✈️ Depart via return flight\n\n"
                "*Note: This is mock data for testing. Real data would include specific times, prices, and booking links.*"
            )
        
        # Default response
        return (
            "Mock response: I've processed your request.\n"
            "In production mode with API keys, this would provide detailed AI-generated content.\n"
            "The system is working correctly in offline/mock mode."
        )


def build_llm():
    """Build LLM with fallback to intelligent mock if no API key."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.info("OPENAI_API_KEY not set; using MockLLM (offline mode).")
        return MockLLM()
    return ChatOpenAI(
        model="nvidia/nemotron-3-nano-30b-a3b:free",
        base_url="https://openrouter.ai/api/v1",
        api_key=SecretStr(api_key),
        temperature=0,
    )


def build_planner_agent():
    """Build agent for itinerary planning and request clarification.
    
    This agent handles:
    - Clarifying user travel requests
    - Creating initial draft itineraries
    - Generating day-by-day plans
    """
    llm = build_llm()
    
    # Define available tools for reference (not actively used in simple mode)
    tools = [
        Tool.from_function(
            func=find_flights.invoke,
            name="find_flights",
            description="Search for flights between origin and destination. Requires: origin (IATA code), destination (IATA code), depart_date (YYYY-MM-DD)."
        ),
        Tool.from_function(
            func=find_hotels.invoke,
            name="find_hotels",
            description="Find hotel options at destination. Requires: destination (city), check_in (YYYY-MM-DD), check_out (YYYY-MM-DD)."
        ),
        Tool.from_function(
            func=attraction_finder.invoke,
            name="attraction_finder",
            description="Find attractions and activities at destination. Requires: destination (city). Optional: interests."
        ),
        Tool.from_function(
            func=weather_checker.invoke,
            name="weather_checker",
            description="Check weather forecast at destination. Requires: destination (city). Optional: date."
        ),
    ]
    
    system_prompt = (
        "You are an expert travel itinerary planner. "
        "You clarify user requests, create detailed day-by-day itineraries, "
        "and incorporate real data from available tools. "
        "Be specific about times, prices, and logistics. "
        "Always include budget estimates and practical tips."
    )
    
    class PlannerAgent:
        """Planner agent that processes messages and generates travel plans."""
        
        def __init__(self, llm, tools, system_prompt):
            self.llm = llm
            self.tools = tools
            self.system_prompt = system_prompt
        
        def invoke(self, message_input):
            """Process input and return planning response."""
            try:
                if isinstance(message_input, dict) and "messages" in message_input:
                    messages = message_input["messages"]
                    if messages:
                        # Prepend system message for context
                        from langchain_core.messages import SystemMessage
                        full_messages = [SystemMessage(content=self.system_prompt)] + list(messages)
                        return self.llm.invoke(full_messages)
                    else:
                        return self.llm.invoke([message_input.get("input", "")])
                else:
                    return self.llm.invoke([message_input])
            except Exception as e:
                logger.error(f"Planner agent error: {e}")
                raise
    
    return PlannerAgent(llm, tools, system_prompt)


def build_refiner_agent():
    """Build agent for refining plans with tool data.
    
    This agent:
    - Takes draft plans and real tool data
    - Merges flight/hotel/attraction/weather info into cohesive itinerary
    - Incorporates user feedback for refinement
    """
    llm = build_llm()
    
    tools = [
        Tool.from_function(
            func=find_flights.invoke,
            name="find_flights",
            description="Reference current flight options"
        ),
        Tool.from_function(
            func=find_hotels.invoke,
            name="find_hotels",
            description="Reference current hotel options"
        ),
    ]
    
    system_prompt = (
        "You are a travel refinement specialist. "
        "Your task is to enhance draft itineraries with real data from tools. "
        "Merge flight times, hotel details, attraction recommendations, and weather into a cohesive plan. "
        "Ensure all details (times, prices, booking info) are incorporated. "
        "Create a final, actionable itinerary ready for the traveler. "
        "When user feedback is provided, prioritize addressing their specific requests."
    )
    
    class RefinerAgent:
        """Refiner agent that enhances plans with tool data."""
        
        def __init__(self, llm, tools, system_prompt):
            self.llm = llm
            self.tools = tools
            self.system_prompt = system_prompt
        
        def invoke(self, message_input):
            """Process refinement request."""
            try:
                if isinstance(message_input, dict) and "messages" in message_input:
                    messages = message_input["messages"]
                    if messages:
                        from langchain_core.messages import SystemMessage
                        full_messages = [SystemMessage(content=self.system_prompt)] + list(messages)
                        return self.llm.invoke(full_messages)
                    else:
                        return self.llm.invoke([message_input.get("input", "")])
                else:
                    return self.llm.invoke([message_input])
            except Exception as e:
                logger.error(f"Refiner agent error: {e}")
                raise
    
    return RefinerAgent(llm, tools, system_prompt)


def build_tool_selector_agent():
    """Build agent that autonomously decides which tools to invoke.
    
    This agent analyzes the current state and decides which tools
    should be called based on:
    - Available data (origin, destination, dates, etc.)
    - User request context
    - What information would enhance the plan
    """
    llm = build_llm()
    
    system_prompt = (
        "You are a decision-making agent. "
        "Based on the provided context, decide which tools should be called to enhance the travel plan. "
        "Output a JSON list of tool names to invoke. "
        "Example: ['find_flights', 'find_hotels', 'attraction_finder', 'weather_checker']. "
        "Only include tools where the required data is available. "
        "Always respond with valid JSON array, even if empty: []"
    )
    
    class ToolSelectorAgent:
        """Agent that decides which tools to invoke based on context."""
        
        def __init__(self, llm, system_prompt):
            self.llm = llm
            self.system_prompt = system_prompt
        
        def invoke(self, message_input):
            """Analyze context and return tool selection."""
            try:
                if isinstance(message_input, dict) and "messages" in message_input:
                    messages = message_input["messages"]
                    if messages:
                        from langchain_core.messages import SystemMessage
                        full_messages = [SystemMessage(content=self.system_prompt)] + list(messages)
                        return self.llm.invoke(full_messages)
                    else:
                        return self.llm.invoke([message_input.get("input", "")])
                else:
                    return self.llm.invoke([message_input])
            except Exception as e:
                logger.error(f"Tool selector agent error: {e}")
                raise
    
    return ToolSelectorAgent(llm, system_prompt)


def is_mock_mode() -> bool:
    """Check if system is running in mock mode (no API key)."""
    return MOCK_MODE






