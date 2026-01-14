from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AnyMessage,SystemMessage,HumanMessage,ToolMessage
import os
from typing import Annotated,TypedDict
from agents.tools.tools import find_flights,find_hotels,attraction_finder,weather_checker,generate_pdf_itinerary,email_sender
import logging
from pydantic import SecretStr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

prompt_enhance_sys_pmt=""" """
tvavell_agent_sys_pmt=""" """
email_sys_pmt=""" """
tool_call_pmt=""" """

prompt_enhance_model = ChatOpenAI(
    model="nvidia/nemotron-3-nano-30b-a3b:free",
    base_url="https://openrouter.ai/api/v1",
    api_key=SecretStr(os.getenv("OPENAI_API_KEY")or ""),
    temperature=0
)

create_agent(prompt_enhance_model)

accom_flight_model= ChatOpenAI(
    model="nvidia/nemotron-3-nano-30b-a3b:free",
    base_url="https://openrouter.ai/api/v1",
    api_key=SecretStr(os.getenv("OPENAI_API_KEY")or ""),
    temperature=0
)
create_agent(accom_flight_model,tools=(find_flights,find_hotels))

detail_plan_model= ChatOpenAI(
    model="nvidia/nemotron-3-nano-30b-a3b:free",
    base_url="https://openrouter.ai/api/v1",
    api_key=SecretStr(os.getenv("OPENAI_API_KEY")or ""),
    temperature=0
)
create_agent(detail_plan_model,tools=(attraction_finder,weather_checker))

util_model= ChatOpenAI(
    model="nvidia/nemotron-3-nano-30b-a3b:free",
    base_url="https://openrouter.ai/api/v1",
    api_key=SecretStr(os.getenv("OPENAI_API_KEY")or ""),
    temperature=0
)
create_agent(util_model,tools=(generate_pdf_itinerary,email_sender))


class agentstate(TypedDict):
    pass

class ItineraryAgent:
    pass

class AccommodationAgent:
    pass

class DetailPlanningAgent:
    pass

class UtilityAgent:
    pass

class PromptEnhancementAgent:
    pass






