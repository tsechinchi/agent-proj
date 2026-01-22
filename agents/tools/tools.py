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
load_dotenv("keys.env", override=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
import hashlib
import time
import textwrap
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# Optional dependency: reportlab. Keep import optional so module can be imported
# even if reportlab isn't installed; functions will return friendly errors.
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except Exception:
    HAS_REPORTLAB = False

# Feature flags
ALLOW_AUTO_EMAIL_PDF = os.getenv("ALLOW_AUTO_EMAIL_PDF", "false").lower() == "true"
# Test-only: allow a second, more permissive hotel-offers attempt if the first returns no data.
ALLOW_HOTEL_TEST_RETRY = os.getenv("AMADEUS_TEST_HOTEL_RETRY", "true").lower() == "true"

# API Timeouts (in seconds)
API_TIMEOUT_SHORT = 10
API_TIMEOUT_LONG = 15

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1.5

# Hotel search broadening thresholds
HOTEL_SEARCH_MAX_ATTEMPTS = 12  # Try up to N hotels for availability
HOTEL_FALLBACK_STRATEGIES = ["bestRateOnly=False", "adults=2", "nearby_dates"]

AMADEUS_USE_PROD = False

# Amadeus sandbox-supported cities (limited test inventory)
SANDBOX_CITY_MAP = {
    "paris": {"iata": "PAR", "name": "Paris"},
    "london": {"iata": "LON", "name": "London"},
    "new york": {"iata": "NYC", "name": "New York"},
    "berlin": {"iata": "BER", "name": "Berlin"},
    "rome": {"iata": "ROM", "name": "Rome"},
    "madrid": {"iata": "MAD", "name": "Madrid"},
    "barcelona": {"iata": "BCN", "name": "Barcelona"},
}
SANDBOX_IATA_SET = {v["iata"] for v in SANDBOX_CITY_MAP.values()}
AMADEUS_BASE_HOST = os.getenv("AMADEUS_BASE_HOST", "test.api.amadeus.com")

# Demo/Mock mode warning
_API_KEYS_AVAILABLE = {
    "amadeus": bool(os.getenv("AMADEUS_CLIENT_ID")) or bool(os.getenv("AMADEUS_ID")),
    "openweather": bool(os.getenv("OPENWEATHER_API_KEY")),
    "smtp": bool(os.getenv("GMAIL_USERNAME")),
}
if not any(_API_KEYS_AVAILABLE.values()):
    logger.warning(
        "🔔 Running in DEMO MODE: No API keys configured. "
        "All tool calls will return mock/sample data. "
        "To use real data, set environment variables: "
        "AMADEUS_CLIENT_ID, AMADEUS_CLIENT_SECRET, OPENWEATHER_API_KEY, GMAIL_USERNAME"
    )
else:
    available_apis = [k for k, v in _API_KEYS_AVAILABLE.items() if v]
    logger.info(f"API keys configured for: {', '.join(available_apis)}")


def format_mock_warning(data_str: str) -> str:
    """Add mock data disclaimer if running in demo mode."""
    if not any(_API_KEYS_AVAILABLE.values()):
        return f"{data_str}\n\n⚠️ [DEMO DATA - For planning purposes only. Use real API keys for production.]"
    return data_str


def log_api_request(endpoint: str, params: dict, label: str = "") -> None:
    """Log API request details (sanitized) for observability."""
    # Sanitize: remove secrets from params
    safe_params = {k: v for k, v in params.items() if k.lower() not in ("appid", "api_key", "client_secret", "password")}
    prefix = f"[{label}] " if label else ""
    logger.info(f"{prefix}API REQUEST: {endpoint} params={safe_params}")


def log_api_response(endpoint: str, status: int, body_preview: str, label: str = "", error_details: Optional[dict] = None) -> None:
    """Log API response details for observability."""
    prefix = f"[{label}] " if label else ""
    logger.info(f"{prefix}API RESPONSE: {endpoint} status={status} body_preview={body_preview[:400]}")
    if error_details:
        logger.warning(f"{prefix}API ERROR DETAILS: {error_details}")

def parse_destination(raw: str) -> tuple[str, str]:
    """Return (iata_like, city_like) from a free-form destination string."""
    txt = (raw or "").strip()
    base = txt.split(",")[0].strip() if "," in txt else txt
    if len(base) == 3 and base.isalpha():
        code = base.upper()
        return code, iata_to_city(code)
    # If it's not an IATA code, treat as city name
    return base, base


def iata_to_city(code: str) -> str:
    """Best-effort map from IATA code to city name for downstream lookups."""
    # Only keep sandbox-supported mappings
    key = (code or "").strip().upper()
    for city_name, info in SANDBOX_CITY_MAP.items():
        if key == info["iata"]:
            return info["name"]
    return code


def city_to_iata(city_name: str) -> str | None:
    """Best-effort map from city name to IATA code for Amadeus sandbox fallback.
    
    The Amadeus sandbox doesn't always return cities from keyword search,
    but it does have hotel data for these IATA codes.
    """
    key = (city_name or "").strip().lower()
    info = SANDBOX_CITY_MAP.get(key)
    return info["iata"] if info else None


def validate_date_format(date_str: str, field_name: str = "date") -> tuple[bool, str]:
    """Validate date string is in YYYY-MM-DD format.
    Returns (is_valid, error_message).
    """
    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
        return True, ""
    except ValueError:
        return False, f"error: {field_name} must be in YYYY-MM-DD format, got '{date_str}'"


def supported_city_prompt() -> str:
    names = [info["name"] for info in SANDBOX_CITY_MAP.values()]
    iatas = [info["iata"] for info in SANDBOX_CITY_MAP.values()]
    return (
        "Amadeus sandbox supports hotels for: "
        + ", ".join(sorted(names))
        + " (IATA: "
        + ", ".join(sorted(iatas))
        + ")."
    )


def get_amadeus_token(client_id: str, client_secret: str) -> str | None:
    """Fetch OAuth2 token from Amadeus test endpoint. Returns access_token or None.

    Logs response text for debugging when token is missing or request fails.
    """
    try:
        token_url = f"https://{AMADEUS_BASE_HOST}/v1/security/oauth2/token"
        resp = requests.post(
            token_url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=API_TIMEOUT_SHORT,
        )
        if resp.status_code != 200:
            logger.warning(f"Amadeus token endpoint returned {resp.status_code}: {resp.text[:500]}")
            resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            logger.warning(f"Amadeus token response missing access_token: {resp.text[:800]}")
            return None
        return token
    except Exception as e:
        logger.warning(f"Failed to obtain Amadeus token: {type(e).__name__} {e}")
        return None


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
    
    # Normalize destination
    dest_code, dest_city = parse_destination(destination)

    amadeus_id = os.getenv("AMADEUS_CLIENT_ID") or os.getenv("AMADEUS_ID")
    amadeus_secret = os.getenv("AMADEUS_CLIENT_SECRET") or os.getenv("AMADEUS_SECRET")

    def _mock_flights():
        carriers = ["AA", "DL", "UA", "BA", "LH", "AF", "KL"]
        base_price = random.randint(200, 800)
        results = []
        for idx in range(1, 4):
            carrier = random.choice(carriers)
            flight_num = random.randint(100, 999)
            price = base_price + random.randint(-100, 200)
            dep_time = f"{depart_date}T{random.randint(6, 20):02d}:{random.randint(0, 59):02d}:00"
            arr_time = f"{depart_date}T{random.randint(10, 23):02d}:{random.randint(0, 59):02d}:00"
            flight_info = f"{carrier}{flight_num}: {origin} {dep_time} -> {dest_code} {arr_time}"
            if return_date:
                ret_dep = f"{return_date}T{random.randint(6, 20):02d}:{random.randint(0, 59):02d}:00"
                ret_arr = f"{return_date}T{random.randint(10, 23):02d}:{random.randint(0, 59):02d}:00"
                # Use parsed destination code to avoid mixing origin/destination
                return_info = f"{carrier}{flight_num+1}: {dest_code} {ret_dep} -> {origin} {ret_arr}"
                flight_info = f"{flight_info} | {return_info}"
            results.append(f"{idx}. ${price} — {flight_info}")
        return format_mock_warning("\n".join(results))

    if not amadeus_id or not amadeus_secret:
        logger.info("AMADEUS credentials not set — using mock flight data")
        return _mock_flights()

    # Obtain OAuth token from Amadeus test environment
    try:
        access_token = get_amadeus_token(amadeus_id, amadeus_secret)
        if not access_token:
            return _mock_flights()

        params = {
            "originLocationCode": origin,
            "destinationLocationCode": dest_code,
            "departureDate": depart_date,
            "adults": adults,
            "max": 3,
        }
        if return_date:
            params["returnDate"] = return_date

        flight_url = f"https://{AMADEUS_BASE_HOST}/v2/shopping/flight-offers"
        resp = requests.get(
            flight_url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=API_TIMEOUT_LONG,
        )
        # If unauthorized, try refresh token once
        if resp.status_code == 401:
            logger.info("Amadeus flight offers returned 401; refreshing token and retrying once")
            access_token = get_amadeus_token(amadeus_id, amadeus_secret)
            if not access_token:
                return _mock_flights()
            resp = requests.get(
                flight_url,
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
    except requests.HTTPError as e:
        logger.warning(f"Amadeus flight search HTTP error; returning mock: {e}")
        return _mock_flights()
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
            address = f"{random.randint(1, 999)} Main St, {dest_city}"
            results.append(f"{idx}. {name} {dest_city} — {address} — ${total_price} ({nights} nights @ ${price_per_night}/night) — {tier}")
        return "\n".join(results) + "\n\n(Mock data - for demo purposes only)"

    # Normalize destination for city-based search
    raw_dest = destination
    _, dest_city = parse_destination(destination)
    logger.info(f"find_hotels called: raw_destination={raw_dest!r} parsed_city={dest_city!r}")

    # Enforce sandbox-supported cities to avoid silent mock fallback
    fallback_iata = city_to_iata(dest_city)
    raw_iata = raw_dest.strip().upper() if isinstance(raw_dest, str) else ""
    is_supported_iata = raw_iata in SANDBOX_IATA_SET
    if not fallback_iata and not is_supported_iata:
        msg = (
            f"error: destination '{dest_city}' is not available in Amadeus sandbox. "
            + supported_city_prompt()
            + "\n\n(Mock data below for planning purposes)\n"
        )
        return msg + _mock_hotels()

    # If user provided IATA code directly and it's supported, honor it
    if is_supported_iata:
        dest_city = iata_to_city(raw_iata)

    amadeus_id = os.getenv("AMADEUS_ID")
    amadeus_secret = os.getenv("AMADEUS_SECRET")

    if not amadeus_id or not amadeus_secret:
        logger.info("AMADEUS credentials not set — using mock hotel data")
        return _mock_hotels()

    # Get token
    try:
        access_token = get_amadeus_token(amadeus_id, amadeus_secret)
        if not access_token:
            return _mock_hotels()

        # Resolve city code via reference-data locations
        loc_url = f"https://{AMADEUS_BASE_HOST}/v1/reference-data/locations"
        loc_resp = requests.get(
            loc_url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"subType": "CITY", "keyword": dest_city, "page[limit]": 1},
            timeout=API_TIMEOUT_SHORT,
        )
        logger.info(f"Amadeus locations lookup status: {loc_resp.status_code}")
        # If unauthorized, refresh token and retry once
        if loc_resp.status_code == 401:
            logger.info("Amadeus locations returned 401; refreshing token and retrying once")
            access_token = get_amadeus_token(amadeus_id, amadeus_secret)
            if not access_token:
                return _mock_hotels()
            loc_resp = requests.get(
                "https://test.api.amadeus.com/v1/reference-data/locations",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"subType": "CITY", "keyword": dest_city, "page[limit]": 1},
                timeout=API_TIMEOUT_SHORT,
            )
        loc_resp.raise_for_status()
        loc_data = loc_resp.json().get("data") or []
        
        city_code = None
        if loc_data:
            city_code = loc_data[0].get("iataCode") or loc_data[0].get("cityCode") or loc_data[0].get("id")
            logger.info(f"Amadeus resolved city_code from API: {city_code}")
        
        # Fallback: if Amadeus sandbox doesn't have the city, try known IATA mapping
        if not city_code:
            fallback_code = city_to_iata(dest_city)
            if fallback_code:
                logger.info(f"Amadeus city lookup returned no results for '{dest_city}', using fallback IATA code: {fallback_code}")
                city_code = fallback_code
            elif raw_iata in SANDBOX_IATA_SET:
                city_code = raw_iata
                logger.info(f"Using user-provided IATA code: {city_code}")
            else:
                logger.warning(f"No city_code found for '{dest_city}' and no fallback IATA mapping available")
                return _mock_hotels()

        params = {
            "cityCode": city_code,
            "checkInDate": check_in,
            "checkOutDate": check_out,
            "roomQuantity": 1,
            "adults": 1,
            "bestRateOnly": True,
        }

        def _fetch_hotel_ids_by_city(city_code_inner: str, token: str) -> list:
            """Query the Hotel List (by-city) endpoint to obtain hotelIds usable in sandbox.

            Returns a list of hotel id strings (may be empty).
            """
            try:
                by_city_url = f"https://{AMADEUS_BASE_HOST}/v1/reference-data/locations/hotels/by-city"
                resp_ids = requests.get(
                    by_city_url,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"cityCode": city_code_inner},
                    timeout=API_TIMEOUT_SHORT,
                )
                logger.info(f"Amadeus hotel-list by-city status: {resp_ids.status_code}")
                try:
                    logger.info(f"Amadeus hotel-list body (truncated): {resp_ids.text[:800]}")
                except Exception:
                    pass
                resp_ids.raise_for_status()
                data_ids = resp_ids.json().get("data") or []
                ids = []
                for item in data_ids:
                    hid = None
                    if isinstance(item, dict):
                        # Some sandbox shapes nest hotel info under 'hotel'
                        hotelobj = item.get("hotel") or item
                        if isinstance(hotelobj, dict):
                            hid = hotelobj.get("hotelId") or hotelobj.get("id")
                        if not hid:
                            hid = item.get("hotelId") or item.get("id")
                    if hid:
                        ids.append(str(hid))
                return ids
            except Exception as e:
                logger.info(f"Failed to fetch hotel ids by city: {e}")
                return []

        def _call_hotel_offers(call_params: dict, label: str, retry_count: int = 0) -> tuple[list, dict, int, str]:
            """Call hotel offers endpoint with retry support. Returns (offers, data, status, error_reason)."""
            offers_url = f"https://{AMADEUS_BASE_HOST}/v3/shopping/hotel-offers"
            log_api_request(offers_url, call_params, f"hotel-offers:{label}")
            
            try:
                resp_inner = requests.get(
                    offers_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=call_params,
                    timeout=API_TIMEOUT_LONG,
                )
            except requests.exceptions.Timeout as e:
                logger.warning(f"Amadeus hotel-offers [{label}] timeout: {e}")
                return [], {}, 0, "timeout"
            except requests.exceptions.RequestException as e:
                logger.warning(f"Amadeus hotel-offers [{label}] request failed: {e}")
                return [], {}, 0, f"request_error:{type(e).__name__}"

            log_api_response(offers_url, resp_inner.status_code, resp_inner.text, f"hotel-offers:{label}")
            
            # Parse JSON body (even on errors)
            try:
                data_inner = resp_inner.json()
            except Exception:
                data_inner = {}
            
            offers_inner = data_inner.get("data") or []
            error_reason = ""
            
            # Extract error details for observability
            if resp_inner.status_code >= 400:
                errors = data_inner.get("errors", [])
                if errors:
                    error_codes = [e.get("code") for e in errors if isinstance(e, dict)]
                    error_titles = [e.get("title", "") for e in errors if isinstance(e, dict)]
                    error_reason = f"API_ERROR:{error_codes}:{error_titles}"
                    log_api_response(offers_url, resp_inner.status_code, resp_inner.text, f"hotel-offers:{label}", 
                                     {"error_codes": error_codes, "error_titles": error_titles})
                    
                    # Handle specific error codes
                    if 3664 in error_codes:  # NO_ROOMS_AVAILABLE
                        error_reason = "NO_ROOMS_AVAILABLE"
                    elif 429 == resp_inner.status_code and retry_count < MAX_RETRIES:
                        # Rate limited: wait and retry
                        logger.info(f"Rate limited on hotel-offers [{label}], retrying in {RETRY_DELAY_SECONDS}s (attempt {retry_count + 1}/{MAX_RETRIES})")
                        time.sleep(RETRY_DELAY_SECONDS * (retry_count + 1))  # Exponential backoff
                        return _call_hotel_offers(call_params, f"{label}:retry{retry_count + 1}", retry_count + 1)
            
            logger.info(
                f"Amadeus hotel-offers [{label}] parsed: keys={list(data_inner.keys()) if isinstance(data_inner, dict) else []} "
                f"offers_count={len(offers_inner)} status={resp_inner.status_code} error_reason={error_reason or 'none'}"
            )
            return offers_inner, data_inner, resp_inner.status_code, error_reason

        offers, data, status, error_reason = _call_hotel_offers(params, "primary")
        all_hotel_errors = []  # Track errors for observability
        if error_reason:
            all_hotel_errors.append(f"primary:{error_reason}")

        # Optional: retry with relaxed filters in test mode to broaden results.
        if not offers and ALLOW_HOTEL_TEST_RETRY:
            # Strategy 1: Relax bestRateOnly and try adults=2
            retry_params = dict(params)
            retry_params.update({"bestRateOnly": False, "adults": 2})
            offers, data, status, error_reason = _call_hotel_offers(retry_params, "retry:relaxed_params")
            if error_reason:
                all_hotel_errors.append(f"relaxed:{error_reason}")

        # If still no offers, attempt to fetch hotelIds via Hotel List and retry with hotelIds.
        if not offers and ALLOW_HOTEL_TEST_RETRY:
            hotel_ids = _fetch_hotel_ids_by_city(city_code, access_token)
            logger.info(f"Hotel ID lookup returned {len(hotel_ids)} hotels for {city_code}")
            if hotel_ids:
                # Try each hotel id individually (some sandbox ids return NO_ROOMS);
                # skip hotels with NO_ROOMS and continue to next.
                found = False
                no_rooms_count = 0
                for idx, hid in enumerate(hotel_ids[:HOTEL_SEARCH_MAX_ATTEMPTS]):
                    id_params = {
                        "hotelIds": hid,
                        "checkInDate": check_in,
                        "checkOutDate": check_out,
                        "roomQuantity": 1,
                        "adults": 1,
                        "bestRateOnly": True,
                    }
                    offers, data, status, error_reason = _call_hotel_offers(id_params, f"hotelId:{hid}")
                    
                    # Track NO_ROOMS errors but continue trying other hotels
                    if error_reason == "NO_ROOMS_AVAILABLE":
                        no_rooms_count += 1
                        logger.info(f"Hotel {hid} has no rooms available, trying next ({no_rooms_count} no-rooms so far)")
                        continue
                    elif error_reason:
                        all_hotel_errors.append(f"{hid}:{error_reason}")
                        # On non-NO_ROOMS errors, still continue to try other hotels
                        continue
                    
                    if offers:
                        found = True
                        logger.info(f"Found available offers at hotel {hid} (attempt {idx + 1}/{min(len(hotel_ids), HOTEL_SEARCH_MAX_ATTEMPTS)})")
                        break

                if not found and no_rooms_count > 0:
                    logger.warning(f"Exhausted {no_rooms_count} hotels with NO_ROOMS_AVAILABLE - dates may be fully booked")
                    all_hotel_errors.append(f"no_rooms_all:{no_rooms_count}_hotels")

                if not found and len(hotel_ids) >= 3:
                    # Try a batch call as last resort with relaxed params
                    id_params = {
                        "hotelIds": ",".join(hotel_ids[:5]),
                        "checkInDate": check_in,
                        "checkOutDate": check_out,
                        "roomQuantity": 1,
                        "adults": 2,  # Broadened
                        "bestRateOnly": False,  # Broadened
                    }
                    offers, data, status, error_reason = _call_hotel_offers(id_params, "hotelIds:batch:relaxed")
                    if error_reason:
                        all_hotel_errors.append(f"batch:{error_reason}")
        
        # Log summary of all attempted errors for observability
        if all_hotel_errors and not offers:
            logger.warning(f"Hotel search exhausted all strategies. Error summary: {all_hotel_errors}")

        if not offers:
            partial_msg = (
                f"⚠️ PARTIAL RESULTS: No live hotel offers available for {city_code} on {check_in} to {check_out}.\n"
                f"Reason: All queried hotels returned NO_ROOMS_AVAILABLE or API errors.\n"
                f"Suggestion: Try different dates or a nearby city.\n\n"
                f"(Fallback mock data below for planning purposes)\n"
            )
            return partial_msg + _mock_hotels()

        results = []
        for idx, off in enumerate(offers[:5], start=1):
            hotel = off.get("hotel", {})
            name = hotel.get("name") or json.dumps(hotel)
            price = (off.get("offers") or [{}])[0].get("price", {}).get("total")
            address = ", ".join(hotel.get("address", {}).get("lines", []) or [])
            results.append(f"{idx}. {name} — {address} — ${price}")

        return "\n".join(results)
    except requests.HTTPError as e:
        logger.warning(f"Amadeus hotel search HTTP error; returning mock: {e}")
        return _mock_hotels()
    except Exception as e:
        logger.error(f"Amadeus hotel search error: {e}")
        return _mock_hotels()

@tool(args_schema=AttractionInput)
def attraction_finder(destination: str, interests: Optional[str] = None) -> str:
    """List attractions in a city using free Wikipedia API (no API key required).
    Searches Wikipedia for destination information and extracts key attractions.
    Includes retry logic and multiple query strategies for robustness.
    """
    _, city = parse_destination(destination)
    
    # Validate input
    if not city or len(city.strip()) < 2:
        logger.warning(f"attraction_finder: invalid destination '{destination}'")
        return f"error: invalid destination '{destination}' - please provide a valid city name"
    
    # Multiple query strategies for better results
    query_strategies = [
        f"{city} tourist attractions",
        f"Tourism in {city}",
        f"{city} landmarks",
        f"{city} points of interest",
    ]
    if interests:
        # Prepend interest-specific query
        query_strategies.insert(0, f"{city} {interests}")
    
    search_url = "https://en.wikipedia.org/w/api.php"
    last_error = None
    
    for strategy_idx, search_query in enumerate(query_strategies):
        for retry in range(MAX_RETRIES):
            search_params = {
                "action": "opensearch",
                "search": search_query,
                "limit": 8,
                "format": "json"
            }
            
            log_api_request(search_url, search_params, f"wikipedia:attraction:{strategy_idx}")
            
            try:
                resp = requests.get(
                    search_url,
                    params=search_params,
                    headers={"User-Agent": "travel-planner-demo/1.0 (contact: demo@example.com)"},
                    timeout=API_TIMEOUT_SHORT,
                )
                
                log_api_response(search_url, resp.status_code, resp.text, f"wikipedia:attraction:{strategy_idx}")
                
                # Handle rate limiting with retry
                if resp.status_code == 429:
                    logger.warning(f"Wikipedia rate limited, retry {retry + 1}/{MAX_RETRIES}")
                    time.sleep(RETRY_DELAY_SECONDS * (retry + 1))
                    continue
                
                resp.raise_for_status()
                data = resp.json()
                
                # Validate response structure: opensearch returns [query, [titles], [descriptions], [urls]]
                if not isinstance(data, list) or len(data) < 4:
                    logger.warning(f"Wikipedia returned unexpected format: {type(data)}, len={len(data) if isinstance(data, list) else 'N/A'}")
                    continue
                
                titles = data[1] if isinstance(data[1], list) else []
                descriptions = data[2] if isinstance(data[2], list) else []
                urls = data[3] if isinstance(data[3], list) else []
                
                logger.info(f"Attraction search (Wikipedia): query={search_query!r}, city={city!r}, found={len(titles)}")
                
                # Filter out irrelevant results (e.g., disambiguation pages)
                results = []
                for idx, (title, desc, url) in enumerate(zip(titles, descriptions, urls), start=1):
                    # Skip disambiguation or stub pages
                    if "disambiguation" in title.lower() or "may refer to" in desc.lower():
                        continue
                    results.append(f"{idx}. {title} — {desc or 'No description'} — {url}")
                
                if results:
                    return "\n".join(results[:5])  # Return top 5 relevant results
                
                # No results from this query, try next strategy
                logger.info(f"Query '{search_query}' returned no usable results, trying next strategy")
                break  # Break retry loop, move to next strategy
                
            except requests.exceptions.Timeout:
                last_error = "timeout"
                logger.warning(f"Wikipedia timeout on attempt {retry + 1}/{MAX_RETRIES}")
                time.sleep(RETRY_DELAY_SECONDS)
            except requests.HTTPError as e:
                last_error = f"HTTP {e.response.status_code if e.response else 'unknown'}"
                logger.warning(f"Wikipedia HTTP error: {e}")
                if e.response and e.response.status_code >= 500:
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue  # Retry on server errors
                break  # Don't retry on client errors
            except Exception as e:
                last_error = str(e)
                logger.error(f"Attraction search error: {type(e).__name__}: {e}")
                break
    
    # All strategies exhausted
    logger.warning(f"attraction_finder: all query strategies failed for '{city}'. Last error: {last_error}")
    return (
        f"⚠️ PARTIAL RESULTS: Could not fetch live attraction data for {city}.\n"
        f"Reason: {last_error or 'No results from Wikipedia'}\n\n"
        f"Suggested attractions (general recommendations):\n"
        f"1. Historic city center / old town of {city}\n"
        f"2. Local museums and cultural sites in {city}\n"
        f"3. Popular restaurants and food districts in {city}\n"
        f"4. Parks and scenic viewpoints in {city}\n"
        f"5. Shopping districts and local markets in {city}"
    )

@tool(args_schema=WeatherInput)
def weather_checker(destination: str, date: Optional[str] = None) -> str:
    """Check current weather or forecast for a city using OpenWeather.

    - Reads API key from environment variable `OPENWEATHER_API_KEY`.
    - If `date` is empty, returns current weather.
    - If `date` provided (YYYY-MM-DD), attempts to return forecast for that date (up to ~5 days ahead).
    """
    _, city = parse_destination(destination)
    api_key = os.getenv("OPENWEATHER_API_KEY")
    # If no API key is provided, use a deterministic mock weather response
    if not api_key:
        logger.info("OPENWEATHER_API_KEY not set — using mock weather data")

        def _mock_weather(dest: str, d: Optional[str] = None) -> str:
            seed_input = f"{dest}:{d or 'now'}"
            seed = int(hashlib.sha256(seed_input.encode()).hexdigest(), 16) % (2 ** 32)
            rnd = random.Random(seed)
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
            return _mock_weather(city, date)
        return _mock_weather(city, None)

    try:
        if not date:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {"q": city, "appid": api_key, "units": "metric"}
            resp = requests.get(url, params=params, timeout=API_TIMEOUT_SHORT)
            resp.raise_for_status()
            data = resp.json()
            desc = data.get("weather", [{}])[0].get("description", "unknown")
            temp = data.get("main", {}).get("temp")
            feels = data.get("main", {}).get("feels_like")
            humidity = data.get("main", {}).get("humidity")
            logger.info(f"Weather check: city={city}")
            return f"Current weather in {city}: {desc}, {temp}°C (feels like {feels}°C), humidity {humidity}%"

        # date provided: validate and fetch forecast
        is_valid, err_msg = validate_date_format(date, "date")
        if not is_valid:
            return err_msg
        
        target = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        today = datetime.date.today()
        if target < today:
            return "error: historical data not supported by this tool"

        url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {"q": city, "appid": api_key, "units": "metric"}
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
        logger.info(f"Weather forecast: city={city} date={date}")
        return f"Forecast for {city} on {date} ({dt_txt}): {desc}, {temp}°C, humidity {humidity}%"
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
    if not HAS_REPORTLAB:
        return "error: missing dependency 'reportlab'. Install with: pip install reportlab"

    try:
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

    # smtp and email.mime imports are provided at module top
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

