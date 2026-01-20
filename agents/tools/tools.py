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
from dotenv import load_dotenv
import json
import random

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
import hashlib

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
    """Search for flights using free mock data (no API key required).
    Returns top 3 sample offers formatted with price and segment details.
    For production, integrate with Skyscanner API or other free alternatives.
    """
    # Validate date formats
    is_valid, err_msg = validate_date_format(depart_date, "depart_date")
    if not is_valid:
        return err_msg
    
    if return_date:
        is_valid, err_msg = validate_date_format(return_date, "return_date")
        if not is_valid:
            return err_msg
    
    # Try Amadeus free dev APIs if API keys are provided. Fall back to mock data otherwise.
    # Support a couple common env var names for compatibility
    amadeus_id = os.getenv("AMADEUS_CLIENT_ID") or os.getenv("AMADEUS_ID")
    amadeus_secret = os.getenv("AMADEUS_CLIENT_SECRET") or os.getenv("AMADEUS_SECRET")

    def _mock_flights():
        import random
        carriers = ["AA", "DL", "UA", "BA", "LH", "AF", "KL"]
        base_price = random.randint(200, 800)
        results = []
        for idx in range(1, 4):
            carrier = random.choice(carriers)
            flight_num = random.randint(100, 999)
            price = base_price + random.randint(-100, 200)
            dep_time = f"{depart_date}T{random.randint(6, 20):02d}:{random.randint(0, 59):02d}:00"
            arr_time = f"{depart_date}T{random.randint(10, 23):02d}:{random.randint(0, 59):02d}:00"
            flight_info = f"{carrier}{flight_num}: {origin} {dep_time} -> {destination} {arr_time}"
            if return_date:
                ret_dep = f"{return_date}T{random.randint(6, 20):02d}:{random.randint(0, 59):02d}:00"
                ret_arr = f"{return_date}T{random.randint(10, 23):02d}:{random.randint(0, 59):02d}:00"
                return_info = f"{carrier}{flight_num+1}: {destination} {ret_dep} -> {origin} {ret_arr}"
                flight_info = f"{flight_info} | {return_info}"
            results.append(f"{idx}. ${price} — {flight_info}")
        return "\n".join(results) + "\n\n(Mock data - for demo purposes only)"

    if not amadeus_id or not amadeus_secret:
        logger.info("AMADEUS credentials not set — using mock flight data")
        return _mock_flights()

    # Obtain OAuth token from Amadeus test environment
    try:
        token_resp = requests.post(
            "https://test.api.amadeus.com/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": amadeus_id,
                "client_secret": amadeus_secret,
            },
            timeout=API_TIMEOUT_SHORT,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            logger.warning("Amadeus token response missing access_token — falling back to mock")
            return _mock_flights()

        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": depart_date,
            "adults": adults,
            "max": 3,
        }
        if return_date:
            params["returnDate"] = return_date

        resp = requests.get(
            "https://test.api.amadeus.com/v2/shopping/flight-offers",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=API_TIMEOUT_LONG,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("data") or []
        if not items:
            return "No flight offers found (Amadeus).\n\n(Mock data below)\n" + _mock_flights()

        results = []
        for idx, item in enumerate(items[:3], start=1):
            # price extraction is best-effort; Amadeus may use different fields
            price = (item.get("price") or {}).get("grandTotal") or (item.get("price") or {}).get("total")
            itineraries = item.get("itineraries", [])
            segs = []
            for itin in itineraries:
                for seg in itin.get("segments", []):
                    carrier = seg.get("carrierCode")
                    num = seg.get("number")
                    dep = seg.get("departure", {}).get("iataCode")
                    arr = seg.get("arrival", {}).get("iataCode")
                    dep_t = seg.get("departure", {}).get("at")
                    arr_t = seg.get("arrival", {}).get("at")
                    segs.append(f"{carrier}{num}: {dep} {dep_t} -> {arr} {arr_t}")
            info = " | ".join(segs) if segs else json.dumps(item)
            results.append(f"{idx}. ${price} — {info}")

        return "\n".join(results)
    except Exception as e:
        logger.error(f"Amadeus flight search error: {e}")
        return _mock_flights()

@tool(args_schema=HotelSearchInput)
def find_hotels(destination: str, check_in: str, check_out: str, budget: Optional[str] = None) -> str:
    """Find hotel options using free mock data (no API key required).
    Returns sample hotel offers with realistic pricing.
    For production, integrate with Booking.com API or other free alternatives.
    """
    # Validate date formats
    is_valid, err_msg = validate_date_format(check_in, "check_in")
    if not is_valid:
        return err_msg
    
    is_valid, err_msg = validate_date_format(check_out, "check_out")
    if not is_valid:
        return err_msg
    
    # Try Amadeus hotel search if credentials present; otherwise use deterministic mock
    amadeus_id = os.getenv("AMADEUS_CLIENT_ID") or os.getenv("AMDEUS_CLIENT_ID")
    amadeus_secret = os.getenv("AMADEUS_CLIENT_SECRET") or os.getenv("AMDEUS_CLIENT_SECRET")

    def _mock_hotels():
        
        check_in_dt = datetime.datetime.strptime(check_in, "%Y-%m-%d")
        check_out_dt = datetime.datetime.strptime(check_out, "%Y-%m-%d")
        nights = (check_out_dt - check_in_dt).days
        hotel_types = [
            ("Grand Hotel", "luxury", 200, 400),
            ("Comfort Inn", "mid-range", 80, 150),
            ("Budget Hostel", "budget", 30, 60),
            ("Boutique Suites", "mid-range", 120, 200),
            ("Downtown Lodge", "budget", 50, 90)
        ]
        results = []
        for idx, (name, tier, min_price, max_price) in enumerate(hotel_types, start=1):
            price_per_night = random.randint(min_price, max_price)
            total_price = price_per_night * nights
            address = f"{random.randint(1, 999)} Main St, {destination}"
            results.append(f"{idx}. {name} {destination} — {address} — ${total_price} ({nights} nights @ ${price_per_night}/night) — {tier}")
        return "\n".join(results) + "\n\n(Mock data - for demo purposes only)"

    if not amadeus_id or not amadeus_secret:
        logger.info("AMADEUS credentials not set — using mock hotel data")
        return _mock_hotels()

    # Get token
    try:
        token_resp = requests.post(
            "https://test.api.amadeus.com/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": amadeus_id,
                "client_secret": amadeus_secret,
            },
            timeout=API_TIMEOUT_SHORT,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            logger.warning("Amadeus token response missing access_token — falling back to mock hotels")
            return _mock_hotels()

        # Resolve city code via reference-data locations
        loc_resp = requests.get(
            "https://test.api.amadeus.com/v1/reference-data/locations",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"subType": "CITY", "keyword": destination, "page[limit]": 1},
            timeout=API_TIMEOUT_SHORT,
        )
        loc_resp.raise_for_status()
        loc_data = loc_resp.json().get("data") or []
        if not loc_data:
            return _mock_hotels()
        city_code = loc_data[0].get("iataCode") or loc_data[0].get("cityCode") or loc_data[0].get("id")
        if not city_code:
            return _mock_hotels()

        params = {
            "cityCode": city_code,
            "checkInDate": check_in,
            "checkOutDate": check_out,
            "roomQuantity": 1,
            "adults": 1,
            "bestRateOnly": True,
        }
        resp = requests.get(
            "https://test.api.amadeus.com/v2/shopping/hotel-offers",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=API_TIMEOUT_LONG,
        )
        resp.raise_for_status()
        data = resp.json()
        offers = data.get("data") or []
        if not offers:
            return "No hotel offers found (Amadeus).\n\n(Mock data below)\n" + _mock_hotels()

        results = []
        for idx, off in enumerate(offers[:5], start=1):
            hotel = off.get("hotel", {})
            name = hotel.get("name") or json.dumps(hotel)
            price = (off.get("offers") or [{}])[0].get("price", {}).get("total")
            address = ", ".join(hotel.get("address", {}).get("lines", []) or [])
            results.append(f"{idx}. {name} — {address} — ${price}")

        return "\n".join(results)
    except Exception as e:
        logger.error(f"Amadeus hotel search error: {e}")
        return _mock_hotels()

@tool(args_schema=AttractionInput)
def attraction_finder(destination: str, interests: Optional[str] = None) -> str:
    """List attractions in a city using free Wikipedia API (no API key required).
    Searches Wikipedia for destination information and extracts key attractions.
    """
    try:
        # Use Wikipedia API (completely free, no key needed)
        search_query = f"{destination} tourism attractions"
        if interests:
            search_query = f"{destination} {interests}"
        
        # Search Wikipedia
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "opensearch",
            "search": search_query,
            "limit": 5,
            "format": "json"
        }
        
        resp = requests.get(search_url, params=search_params, timeout=API_TIMEOUT_SHORT)
        resp.raise_for_status()
        data = resp.json()
        
        if len(data) < 4 or not data[1]:
            return f"No attractions found for {destination} on Wikipedia."
        
        titles = data[1]
        descriptions = data[2]
        urls = data[3]
        
        logger.info(f"Attraction search (Wikipedia): {destination}, found {len(titles)} results")
        
        results = []
        for idx, (title, desc, url) in enumerate(zip(titles, descriptions, urls), start=1):
            results.append(f"{idx}. {title} — {desc} — {url}")
        
        if not results:
            return f"No specific attractions found for {destination}. Try a more specific search."
        
        return "\n".join(results)
    except requests.HTTPError as e:
        logger.error(f"Wikipedia API HTTP error: {e}")
        return f"error: Wikipedia API error: {e}"
    except Exception as e:
        logger.error(f"Attraction search error: {e}")
        return f"error: {e}"

@tool(args_schema=WeatherInput)
def weather_checker(destination: str, date: Optional[str] = None) -> str:
    """Check current weather or forecast for a city using OpenWeather.

    - Reads API key from environment variable `OPENWEATHER_API_KEY`.
    - If `date` is empty, returns current weather.
    - If `date` provided (YYYY-MM-DD), attempts to return forecast for that date (up to ~5 days ahead).
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    # If no API key is provided, use a deterministic mock weather response
    if not api_key:
        logger.info("OPENWEATHER_API_KEY not set — using mock weather data")

        def _mock_weather(dest: str, d: Optional[str] = None) -> str:
            seed_input = f"{dest}:{d or 'now'}"
            seed = int(hashlib.sha256(seed_input.encode()).hexdigest(), 16) % (2 ** 32)
            rnd = __import__("random").Random(seed)
            desc_opts = [
                "clear sky",
                "few clouds",
                "scattered clouds",
                "light rain",
                "moderate rain",
                "overcast clouds",
                "thunderstorm",
                "snow",
            ]
            desc = rnd.choice(desc_opts)
            temp = round(rnd.uniform(5.0, 30.0), 1)
            feels = round(temp + rnd.uniform(-3.0, 3.0), 1)
            humidity = rnd.randint(30, 90)
            if not d:
                return f"Mock current weather in {dest}: {desc}, {temp}°C (feels like {feels}°C), humidity {humidity}%"
            return f"Mock forecast for {dest} on {d}: {desc}, {temp}°C, humidity {humidity}%"

        # If date provided, validate and return mock forecast
        if date:
            is_valid, err_msg = validate_date_format(date, "date")
            if not is_valid:
                return err_msg
            return _mock_weather(destination, date)
        return _mock_weather(destination, None)

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
    """Send email with optional attachment using SMTP (Gmail or custom SMTP server).
    Requires: SMTP_EMAIL, SMTP_PASSWORD, SMTP_SERVER (optional), SMTP_PORT (optional)
    Input: recipient_email, subject, body, attachment_path (optional).
    Output: 'Email sent successfully' on success or 'error: <msg>' on failure.
    """

    if not ALLOW_AUTO_EMAIL_PDF:
        return "Human approval required before sending email. Set ALLOW_AUTO_EMAIL_PDF=true to enable."

    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")  # Default to Gmail
    smtp_port = int(os.getenv("SMTP_PORT", "587"))  # Default TLS port
    
    if not smtp_email or not smtp_password:
        return "error: SMTP_EMAIL and SMTP_PASSWORD must be set in environment. For Gmail, use an app-specific password."
    
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_email
        msg["To"] = recipient_email
        msg["Subject"] = subject
        

        msg.attach(MIMEText(body, "plain"))
        
        # Add attachment if provided
        if attachment_path:
            if not os.path.isfile(attachment_path):
                return f"error: attachment not found: {attachment_path}"
            
            with open(attachment_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {os.path.basename(attachment_path)}",
            )
            msg.attach(part)
        
        # Connect and send
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        
        logger.info(f"Email sent successfully to {recipient_email}")
        return f"Email sent successfully to {recipient_email}"
    
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return f"error: failed to send email: {e}"

