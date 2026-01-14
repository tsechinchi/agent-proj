from langchain.tools import tool 
from typing import Optional
from pydantic import BaseModel, Field

# --- Planning & Search Schemas ---

class ItineraryInput(BaseModel):
    destination: str = Field(description="The main city or country for the trip")
    days: int = Field(description="Total duration of the trip in days")
    interests: Optional[str] = Field(None, description="User's specific interests (e.g., 'history', 'food', 'hiking')")

class FlightSearchInput(BaseModel):
    origin: str = Field(description="Three-letter IATA airport code for origin (e.g., JFK, LHR)")
    destination: str = Field(description="Three-letter IATA airport code for destination")
    depart_date: str = Field(description="Departure date in YYYY-MM-DD format")
    return_date: Optional[str] = Field(None, description="Return date in YYYY-MM-DD format")

class HotelSearchInput(BaseModel):
    destination: str = Field(description="City or region to search for hotels")
    check_in: str = Field(description="Check-in date in YYYY-MM-DD format")
    check_out: str = Field(description="Check-out date in YYYY-MM-DD format")
    budget: Optional[str] = Field(None, description="Budget range or tier (e.g., 'low', '$200/night', 'luxury')")

class AttractionInput(BaseModel):
    destination: str = Field(description="City or region to find attractions in")
    interests: Optional[str] = Field(None, description="Specific type of attractions (e.g., 'museums', 'parks')")

class TransportInput(BaseModel):
    destination: str = Field(description="City where transport is needed")
    preferences: Optional[str] = Field(None, description="Type of transport (e.g., 'rental car', 'public transit', 'private driver')")

# --- Information & Logistics Schemas ---

class WeatherInput(BaseModel):
    destination: str = Field(description="City to check weather for")
    date: Optional[str] = Field(None, description="Specific date for forecast in YYYY-MM-DD (leave empty for current forecast)")

class VisaInput(BaseModel):
    nationality: str = Field(description="The citizenship/passport country of the traveler")
    destination: str = Field(description="The country the traveler is visiting")

# --- Action & Output Schemas ---

class PDFInput(BaseModel):
    itinerary_details: str = Field(description="The complete, formatted string of the final itinerary to convert to PDF")

class EmailInput(BaseModel):
    recipient_email: str = Field(description="The user's email address")
    subject: str = Field(description="Subject line for the email")
    body: str = Field(description="The main content of the email")
    attachment_path: Optional[str] = Field(None, description="File path to the generated PDF (if any)")

@tool
def prompt_enhancer(prompt: str) -> str:
   return "0"

@tool(args_schema=ItineraryInput)
def plan_itineryary(destination: str, days: int, interests: Optional[str] = None) -> str:
   return "0"

@tool(args_schema=FlightSearchInput)
def find_flights(origin: str, destination: str, depart_date: str, return_date: str) -> str:
   return "0"

@tool(args_schema=HotelSearchInput)
def find_hotels(destination: str, check_in: str, check_out: str, budget: Optional[str] = None) -> str:
   return "0"

@tool(args_schema=AttractionInput)
def attraction_finder(destination: str, interests: Optional[str] = None) -> str:
   return "0"

@tool(args_schema=WeatherInput)
def weather_checker(destination: str, date: Optional[str] = None) -> str:
   return "0"

@tool(args_schema=VisaInput)
def get_visa_requirement(nationality: str, destination: str) -> str:
   return "0"

@tool(args_schema=TransportInput)
def find_ground_transportation(destination: str, preferences: Optional[str] = None) -> str:
   return "0"

@tool(args_schema=PDFInput)
def generate_pdf_itinerary(itinerary_details: str) -> str:
   return "0"

@tool(args_schema=EmailInput)
def email_sender(recipient_email: str, subject: str, body: str, attachment_path: Optional[str] = None) -> str:
   return "0"
