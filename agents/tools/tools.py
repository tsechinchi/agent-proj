"""Tools:
 - find_flights
 - find_hotels
 - attraction_finder
 - weather_checker
 - generate_pdf_itinerary
 - email_sender
"""
from typing import Optional
import datetime
import base64
import mimetypes
import os
import logging
from email.message import EmailMessage
from pydantic import BaseModel, Field
from langchain.tools import tool
import requests
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Feature flags
ALLOW_AUTO_EMAIL_PDF = os.getenv("ALLOW_AUTO_EMAIL_PDF", "false").lower() == "true"

# API Timeouts (in seconds)
API_TIMEOUT_SHORT = 10
API_TIMEOUT_LONG = 15


def validate_date_format(date_str: str, field_name: str = "date") -> tuple[bool, str]:
    """Validate date string is in YYYY-MM-DD format.
    Returns (is_valid, error_message).
    """
    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
        return True, ""
    except ValueError:
        return False, f"error: {field_name} must be in YYYY-MM-DD format, got '{date_str}'"


# --- Planning & Search Schemas ---
class FlightSearchInput(BaseModel):
    origin: str = Field(description="Three-letter IATA airport code for origin (e.g., JFK, LHR)")
    destination: str = Field(description="Three-letter IATA airport code for destination")
    depart_date: str = Field(description="Departure date in YYYY-MM-DD format")
    return_date: Optional[str] = Field(None, description="Return date in YYYY-MM-DD format")
    adults: int = Field(1, description="Number of adult passengers")
    children: int = Field(0, description="Number of child passengers")

class HotelSearchInput(BaseModel):
    destination: str = Field(description="City or region to search for hotels")
    check_in: str = Field(description="Check-in date in YYYY-MM-DD format")
    check_out: str = Field(description="Check-out date in YYYY-MM-DD format")
    budget: Optional[str] = Field(None, description="Budget range or tier (e.g., 'low', '$200/night', 'luxury')")

class AttractionInput(BaseModel):
    destination: str = Field(description="City or region to find attractions in")
    interests: Optional[str] = Field(None, description="Specific type of attractions (e.g., 'museums', 'parks')")
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

@tool(args_schema=FlightSearchInput)
def find_flights(origin: str, destination: str, depart_date: str, return_date: Optional[str] = None, adults: int = 1, children: int = 0) -> str:
    """Search for flights using the Amadeus Flight Offers API.
    Returns top 3 offers formatted with price and segment details.
    """
    # Validate date formats
    is_valid, err_msg = validate_date_format(depart_date, "depart_date")
    if not is_valid:
        return err_msg
    
    if return_date:
        is_valid, err_msg = validate_date_format(return_date, "return_date")
        if not is_valid:
            return err_msg
    
    client_id = os.getenv("AMADEUS_CLIENT_ID")
    client_secret = os.getenv("AMADEUS_CLIENT_SECRET")
    if not client_id or not client_secret:
        return "error: AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET must be set in environment"

    env = os.getenv("AMADEUS_ENV", "test").lower()
    token_url = "https://test.api.amadeus.com/v1/security/oauth2/token" if env == "test" else "https://api.amadeus.com/v1/security/oauth2/token"
    offers_url = "https://test.api.amadeus.com/v2/shopping/flight-offers" if env == "test" else "https://api.amadeus.com/v2/shopping/flight-offers"

    try:
        # Obtain access token
        token_resp = requests.post(
            token_url,
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
            timeout=API_TIMEOUT_SHORT,
        )
        token_resp.raise_for_status()
        token = token_resp.json().get("access_token")
        if not token:
            return "error: failed to obtain Amadeus access token"

        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": depart_date,
            "adults": adults,
            "max": 10,
        }
        if children and children > 0:
            params["children"] = children
        if return_date:
            params["returnDate"] = return_date

        resp = requests.get(offers_url, headers=headers, params=params, timeout=API_TIMEOUT_LONG)
        resp.raise_for_status()
        data = resp.json()

        offers = data.get("data", [])
        if not offers:
            return f"No flights found for {origin} -> {destination} on {depart_date}."

        logger.info(f"Flight search: {origin} -> {destination}, found {len(offers)} offers")
        results = []
        for idx, offer in enumerate(offers[:3], start=1):
            price = offer.get("price", {}).get("grandTotal") or offer.get("price", {}).get("total") or ""
            itineraries = []
            for itin in offer.get("itineraries", []):
                segs = []
                for seg in itin.get("segments", []):
                    dep = seg.get("departure", {})
                    arr = seg.get("arrival", {})
                    carrier = seg.get("carrierCode", "")
                    number = seg.get("number", "")
                    dep_code = dep.get("iataCode", "")
                    arr_code = arr.get("iataCode", "")
                    dep_time = dep.get("at", "")
                    arr_time = arr.get("at", "")
                    segs.append(f"{carrier}{number}: {dep_code} {dep_time} -> {arr_code} {arr_time}")
                itineraries.append("; ".join(segs))
            results.append(f"{idx}. {price} — {' | '.join(itineraries)}")

        return "\n".join(results)
    except requests.HTTPError as e:
        logger.error(f"Flight search HTTP error: {e}")
        return f"error: HTTP error from Amadeus API: {e}"
    except Exception as e:
        logger.error(f"Flight search error: {e}")
        return f"error: {e}"

@tool(args_schema=HotelSearchInput)
def find_hotels(destination: str, check_in: str, check_out: str, budget: Optional[str] = None) -> str:
    """Find hotel options for destination and date range using the Amadeus Hotel Offers API.

    Environment variables required:
    - `AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET`.
    - `AMADEUS_ENV` optional (default: `test`).
    
    Budget parameter filters results by price tier (if applicable).
    """
    # Validate date formats
    is_valid, err_msg = validate_date_format(check_in, "check_in")
    if not is_valid:
        return err_msg
    
    is_valid, err_msg = validate_date_format(check_out, "check_out")
    if not is_valid:
        return err_msg
    
    client_id = os.getenv("AMADEUS_CLIENT_ID")
    client_secret = os.getenv("AMADEUS_CLIENT_SECRET")
    if not client_id or not client_secret:
        return "error: AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET must be set in environment"

    env = os.getenv("AMADEUS_ENV", "test").lower()
    token_url = "https://test.api.amadeus.com/v1/security/oauth2/token" if env == "test" else "https://api.amadeus.com/v1/security/oauth2/token"
    loc_url = "https://test.api.amadeus.com/v1/reference-data/locations" if env == "test" else "https://api.amadeus.com/v1/reference-data/locations"
    offers_url = "https://test.api.amadeus.com/v2/shopping/hotel-offers" if env == "test" else "https://api.amadeus.com/v2/shopping/hotel-offers"

    try:
        # Obtain access token
        token_resp = requests.post(
            token_url,
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
            timeout=API_TIMEOUT_SHORT,
        )
        token_resp.raise_for_status()
        token = token_resp.json().get("access_token")
        if not token:
            return "error: failed to obtain Amadeus access token"

        headers = {"Authorization": f"Bearer {token}"}

        # Resolve destination to a cityCode (try CITY subtype)
        loc_params = {"keyword": destination, "subType": "CITY"}
        loc_resp = requests.get(loc_url, headers=headers, params=loc_params, timeout=API_TIMEOUT_SHORT)
        loc_resp.raise_for_status()
        loc_data = loc_resp.json().get("data", [])

        city_code = None
        if loc_data:
            first = loc_data[0]
            # try common fields
            city_code = first.get("iataCode") or first.get("id") or first.get("subType")

        # Error if city lookup failed
        if not city_code:
            logger.warning(f"Could not resolve city code for destination: {destination}")
            return f"error: could not resolve destination '{destination}' to a city code. Please try a more specific city name."

        params = {
            "cityCode": city_code,
            "checkInDate": check_in,
            "checkOutDate": check_out,
            "adults": 1,
            "roomQuantity": 1,
            "bestRateOnly": True,
        }
        # Note: budget filtering would require parsing price from API response
        # and comparing to budget parameter if provided

        resp = requests.get(offers_url, headers=headers, params=params, timeout=API_TIMEOUT_LONG)
        resp.raise_for_status()
        data = resp.json()

        offers = data.get("data", [])
        if not offers:
            return f"No hotels found for {destination} ({city_code}) between {check_in} and {check_out}."

        logger.info(f"Hotel search: {destination}, found {len(offers)} offers")
        results = []
        for idx, offer in enumerate(offers[:5], start=1):
            hotel = offer.get("hotel", {})
            name = hotel.get("name", "(no name)")
            address_parts = hotel.get("address", {}).get("lines", []) or []
            city_name = hotel.get("address", {}).get("cityName", "")
            address = ", ".join(address_parts + ([city_name] if city_name else []))

            first_offer = (offer.get("offers") or [{}])[0]
            price = first_offer.get("price", {}).get("total") or first_offer.get("price", {}).get("grandTotal") or ""
            link = first_offer.get("self") or first_offer.get("id") or ""

            results.append(f"{idx}. {name} — {address} — {price} — {link}")

        return "\n".join(results)
    except requests.HTTPError as e:
        logger.error(f"Hotel search HTTP error: {e}")
        return f"error: HTTP error from Amadeus API: {e}"
    except Exception as e:
        logger.error(f"Hotel search error: {e}")
        return f"error: {e}"

@tool(args_schema=AttractionInput)
def attraction_finder(destination: str, interests: Optional[str] = None) -> str:
    """List attractions in a city tailored to user interests.
    """
    api_key = os.getenv("GOOGLE_CLOUD_API_KEY") or os.getenv("GOOGLE_API_KEY")
    cx = os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_CUSTOM_SEARCH_CX") or os.getenv("GOOGLE_CX")

    if not api_key:
        return "error: GOOGLE_CLOUD_API_KEY or GOOGLE_API_KEY not set in environment"
    if not cx:
        return "error: GOOGLE_CSE_ID (custom search engine id) not set in environment"

    # Build a friendly query combining destination and optional interests
    query = f"top attractions in {destination}"
    if interests:
        query = f"{interests} {query}"

    try:
        service = build("customsearch", "v1", developerKey=api_key)
        resp = service.cse().list(q=query, cx=cx, num=10).execute()
        items = resp.get("items", [])

        if not items:
            return f"No attractions found for {destination} (query: '{query}')."

        results = []
        for idx, it in enumerate(items[:5], start=1):
            title = it.get("title", "(no title)")
            snippet = it.get("snippet", "")
            link = it.get("link", "")
            results.append(f"{idx}. {title} — {snippet} — {link}")

        return "\n".join(results)
    except HttpError as e:
        return f"error: Google API HTTP error: {e}"
    except Exception as e:
        return f"error: {e}"

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
            resp = requests.get(url, params=params, timeout=API_TIMEOUT_SHORT)
            resp.raise_for_status()
            data = resp.json()
            desc = data.get("weather", [{}])[0].get("description", "unknown")
            temp = data.get("main", {}).get("temp")
            feels = data.get("main", {}).get("feels_like")
            humidity = data.get("main", {}).get("humidity")
            logger.info(f"Weather check: {destination}")
            return f"Current weather in {destination}: {desc}, {temp}°C (feels like {feels}°C), humidity {humidity}%"

        # date provided: validate and fetch forecast
        is_valid, err_msg = validate_date_format(date, "date")
        if not is_valid:
            return err_msg
        
        target = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        today = datetime.date.today()
        if target < today:
            return "error: historical data not supported by this tool"

        url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {"q": destination, "appid": api_key, "units": "metric"}
        resp = requests.get(url, params=params, timeout=API_TIMEOUT_SHORT)
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
        logger.info(f"Weather forecast: {destination} on {date}")
        return f"Forecast for {destination} on {date} ({dt_txt}): {desc}, {temp}°C, humidity {humidity}%"
    except requests.HTTPError as e:
        logger.error(f"Weather check HTTP error: {e}")
        return f"error: HTTP error: {e}"
    except Exception as e:
        logger.error(f"Weather check error: {e}")
        return f"error: {e}"

@tool(args_schema=PDFInput)
def generate_pdf_itinerary(itinerary_details: str) -> str:
    """Convert itinerary text into a PDF file and return its path."""
    if not ALLOW_AUTO_EMAIL_PDF:
        return "Human approval required before generating PDF. Set ALLOW_AUTO_EMAIL_PDF=true to enable."
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception:
        return "error: missing dependency 'reportlab'. Install with: pip install reportlab"

    try:
        import textwrap
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        filename = f"itinerary_{ts}.pdf"
        c = canvas.Canvas(filename, pagesize=letter)
        width, height = letter
        margin = 72
        max_width = width - margin * 2
        line_height = 14

        lines = []
        for paragraph in itinerary_details.splitlines():
            wrapped = textwrap.wrap(paragraph, width=95) or [""]
            lines.extend(wrapped)

        y = height - margin
        for line in lines:
            if y < margin + line_height:
                c.showPage()
                y = height - margin
            c.drawString(margin, y, line)
            y -= line_height

        c.save()
        return filename
    except Exception as e:
        return f"error: failed to generate PDF: {e}"

@tool(args_schema=EmailInput)
def email_sender(recipient_email: str, subject: str, body: str, attachment_path: Optional[str] = None) -> str:
    """Send email with optional attachment.
    Input: recipient_email, subject, body, attachment_path (optional).
    Output: 'Message Id: <message_id>' on success or 'error: <msg>' on failure.
    """

    if not ALLOW_AUTO_EMAIL_PDF:
        return "Human approval required before sending email. Set ALLOW_AUTO_EMAIL_PDF=true to enable."

    try:
        creds, _ = google.auth.default()
    except Exception as e:
        logger.error(f"Failed to obtain Google credentials: {e}")
        return f"error: failed to obtain Google credentials. Ensure GOOGLE_APPLICATION_CREDENTIALS is set: {e}"
    
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
        message_id = sent.get('id')
        logger.info(f"Email sent successfully: {message_id}")
        return f"Message Id: {message_id}"
    except HttpError as e:
        logger.error(f"Gmail API error: {e}")
        return f"error: Gmail API error: {e}"
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return f"error: {e}"

