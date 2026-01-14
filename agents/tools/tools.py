"""Tools:
 - prompt_enhancer
 - plan_itineryary
 - find_flights
 - find_hotels
 - attraction_finder
 - weather_checker
 - get_visa_requirement
 - find_ground_transportation
 - generate_pdf_itinerary
 - email_sender
 - current_date
"""
from langchain.tools import tool 
from typing import Optional
from pydantic import BaseModel, Field
import datetime
import base64
from email.message import EmailMessage
import mimetypes
import os
import requests
import serpapi



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
    """Enhance or rephrase a user prompt for better results."""
    return "0"

@tool(args_schema=ItineraryInput)
def plan_itineryary(destination: str, days: int, interests: Optional[str] = None) -> str:
    """Generate a high-level itinerary for a destination and duration."""
    return "0"

@tool(args_schema=FlightSearchInput)
def find_flights(origin: str, destination: str, depart_date: str, return_date: str) -> str:
    """Search for flights between two airports on given dates."""
    return "0"

@tool(args_schema=HotelSearchInput)
def find_hotels(destination: str, check_in: str, check_out: str, budget: Optional[str] = None) -> str:
    """Find hotel options for destination and date range."""
    return "0"

@tool(args_schema=AttractionInput)
def attraction_finder(destination: str, interests: Optional[str] = None) -> str:
    """List attractions in a city tailored to user interests."""
    return "0"

@tool(args_schema=WeatherInput)
def weather_checker(destination: str, date: Optional[str] = None) -> str:
   """Check current weather or forecast for a city using OpenWeather.

   - Reads API key from environment variable `OPENWEATHER_API_KEY`.
   - If `date` is empty, returns current weather.
   - If `date` provided (YYYY-MM-DD), attempts to return forecast for that date (up to ~5 days ahead).
   """
   api_key = os.getenv("OPENWEATHER_API_KEY")
   if not api_key:
       return "error: OPENWEATHER_API_KEY not set in environment"

   try:
       if not date:
           url = "https://api.openweathermap.org/data/2.5/weather"
           params = {"q": destination, "appid": api_key, "units": "metric"}
           resp = requests.get(url, params=params, timeout=10)
           resp.raise_for_status()
           data = resp.json()
           desc = data.get("weather", [{}])[0].get("description", "unknown")
           temp = data.get("main", {}).get("temp")
           feels = data.get("main", {}).get("feels_like")
           humidity = data.get("main", {}).get("humidity")
           return f"Current weather in {destination}: {desc}, {temp}°C (feels like {feels}°C), humidity {humidity}%"

       # date provided: try 5-day forecast endpoint (3-hour steps)
       target = datetime.datetime.strptime(date, "%Y-%m-%d").date()
       today = datetime.date.today()
       if target < today:
           return "error: historical data not supported by this tool"

       url = "https://api.openweathermap.org/data/2.5/forecast"
       params = {"q": destination, "appid": api_key, "units": "metric"}
       resp = requests.get(url, params=params, timeout=10)
       resp.raise_for_status()
       data = resp.json()

       matches = []
       for item in data.get("list", []):
           dt = datetime.datetime.fromtimestamp(item.get("dt", 0))
           if dt.date() == target:
               matches.append(item)

       if not matches:
           return f"error: no forecast available for {date} (forecast range ~5 days)"

       # choose entry closest to midday for a representative forecast
       def hour_diff(it):
           return abs(datetime.datetime.fromtimestamp(it.get("dt", 0)).hour - 12)

       best = min(matches, key=hour_diff)
       desc = best.get("weather", [{}])[0].get("description", "unknown")
       temp = best.get("main", {}).get("temp")
       humidity = best.get("main", {}).get("humidity")
       dt_txt = best.get("dt_txt")
       return f"Forecast for {destination} on {date} ({dt_txt}): {desc}, {temp}°C, humidity {humidity}%"
   except requests.HTTPError as e:
       return f"error: HTTP error: {e}"
   except Exception as e:
       return f"error: {e}"

@tool(args_schema=VisaInput)
def get_visa_requirement(nationality: str, destination: str) -> str:
    """Return basic visa entry requirement guidance for a traveler."""
    return "0"

@tool(args_schema=TransportInput)
def find_ground_transportation(destination: str, preferences: Optional[str] = None) -> str:
    """Suggest ground transportation options for a destination."""
    return "0"

@tool(args_schema=PDFInput)
def generate_pdf_itinerary(itinerary_details: str) -> str:
    """Convert itinerary text into a PDF file and return its path."""
    return "0"

@tool(args_schema=EmailInput)
def email_sender(recipient_email: str, subject: str, body: str, attachment_path: Optional[str] = None) -> str:
    """Send email with optional attachment.
    Input: recipient_email, subject, body, attachment_path (optional).
    Output: 'Message Id: <id>' on success or 'error: <msg>' on failure.
    """
    try:
        # Import Google libraries lazily so the module can be used without them installed
        import google.auth
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except Exception:
        return "error: google-api-python-client or google-auth not installed/configured"

    creds, _ = google.auth.default()
    try:
        service = build("gmail", "v1", credentials=creds)
        # get authenticated sender address
        profile = service.users().getProfile(userId="me").execute()
        sender = profile.get("emailAddress")

        message = EmailMessage()
        message["To"] = recipient_email
        if sender:
            message["From"] = sender
        message["Subject"] = subject
        message.set_content(body)

        if attachment_path:
            if not os.path.isfile(attachment_path):
                return f"error: attachment not found: {attachment_path}"
            content_type, _ = mimetypes.guess_type(attachment_path)
            if content_type is None:
                content_type = "application/octet-stream"
            maintype, subtype = content_type.split("/", 1)
            with open(attachment_path, "rb") as fp:
                data = fp.read()
            message.add_attachment(data, maintype=maintype, subtype=subtype, filename=os.path.basename(attachment_path))

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_body = {"raw": encoded_message}
        sent = service.users().messages().send(userId="me", body=send_body).execute()
        return f"Message Id: {sent.get('id')}"
    except HttpError as e:
        return f"error: {e}"
    except Exception as e:
        return f"error: {e}"

