# agent-proj

Multi-agent travel planning system with observability, deployment, and evaluation capabilities.

## 🚀 Quick Start

**New user?** See [QUICK_START.md](QUICK_START.md) for 10-minute setup guide.


---

## Features

### 🤖 Multi-Agent System
- **Request Enhancement Agent**: Clarifies and structures user travel requests
- **Planning Agent**: Creates detailed, actionable itineraries
- **Research Agent**: Gathers real-time travel data and recommendations
- **Logistics Agent**: Handles PDF generation and email delivery
- **✨ FREE APIs Only**: No paid subscriptions required for core functionality

### 🗺️ Smart Destination Handling
The system automatically normalizes common destination typos and aliases:
- **Typos**: `NYK` → `NYC`, `LDN` → `LON`, `MADR` → `MAD`
- **City names**: `New York`, `newyork`, `Manhattan` → `NYC`
- **Airport codes**: `JFK`, `LGA`, `EWR` → `NYC` (for hotel/attraction searches)
- **Alternate names**: `Roma` → `ROM`, `Barca` → `BCN`

This means users can type destinations naturally without worrying about exact IATA codes.

### 🆓 Minimal API Requirements
**Only 1–2 free API keys are recommended:**
1. **OpenRouter** - Free LLM access (nvidia/nemotron-3-nano-30b-a3b:free)
2. **OpenWeatherMap** - Free weather data (1000 calls/day) — optional, the project will
     fall back to a deterministic mock weather response when `OPENWEATHER_API_KEY` is not set.

**Optional / Paid (not required to run):**
- Amadeus — production integrations only; the project uses mock data or
    free alternatives by default.

**What's Free / Mocked by Default:**
- ✅ Flights: Mock data (demo mode)
- ✅ Hotels: Mock data (demo mode)
- ✅ Attractions: Wikipedia API (completely free, no key)
- ✅ Weather: OpenWeatherMap free tier (or deterministic mock when unset)
- ✅ LLM: OpenRouter free models (LLMs fallback to mock when `OPENAI_API_KEY` is unset)

## Installation

```bash
# Clone repository
git clone <repo-url>
cd agent-proj

pip install uv
uv sync

### Minimal API Setup (2 Free APIs)

#### 1. OpenRouter (Free LLM)
Sign up at https://openrouter.ai/
```bash
export OPENAI_API_KEY="sk-or-v1-your-openrouter-key"
```

#### 2. OpenWeatherMap (Free Weather)
Sign up at https://openweathermap.org/api (1000 calls/day free)
```bash
export OPENWEATHER_API_KEY="your-openweather-key"

#### 3. Optional: Amadeus (Flights & Hotels)
For production or sandbox flight and hotel data you can provide Amadeus API
credentials. These are optional — when unset the project uses realistic mock
responses for flights and hotels.

Sign up at https://developers.amadeus.com/ and use the sandbox (`test`) env.

```bash
# Optional (Amadeus sandbox or production)
export AMADEUS_CLIENT_ID="your-client-id"
export AMADEUS_CLIENT_SECRET="your-client-secret"
export AMADEUS_ENV="test"  # or "production"
```

**Amadeus Sandbox Limitations:**
- The sandbox only supports a limited set of cities: **Barcelona, Berlin, London, Madrid, New York, Paris, Rome** (IATA: BCN, BER, LON, MAD, NYC, PAR, ROM)
- The sandbox API can be **unstable** — you may encounter intermittent 500 errors, timeouts, or empty results even for supported cities
- When the sandbox fails, the system automatically falls back to mock data
- For reliable results in demos, consider using mock mode or be prepared for partial data

Notes:
- If `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` are not set the code will
    fall back to deterministic mock flight/hotel results for local development.
- The code accepts common alternate env names for backwards compatibility, but
    prefer `AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET`.
```


### Environment Variables

Create a `keys.env` file (copy from template):

```env
# Required: LLM (Free)
OPENAI_API_KEY="sk-or-v1-your-openrouter-key"

# Required: Weather (Free - 1000 calls/day)
OPENWEATHER_API_KEY="your-openweather-key"


## Usage

### Basic Travel Planning

```bash
python main.py "I want a 5-day trip to Tokyo for food exploration" \
  --origin NRT --destination TYO --depart 2025-06-01 --return 2025-06-05 \
  --check-in 2025-06-01 --check-out 2025-06-05 --interests "food markets, ramen" \
  --duration 5
```

**Note:** Flights and hotels use mock data for demo purposes. For production use, integrate with:
- Free alternatives: Skyscanner API, Booking.com Affiliate API
- Or upgrade to paid APIs: Amadeus, Duffel, Kiwi.com

**Destination Tips:**
- Use standard city names or IATA codes: `NYC`, `Paris`, `LON`, `Rome`
- Common typos are auto-corrected: `NYK` → `NYC`, `LDN` → `LON`
- Amadeus sandbox only supports: Barcelona, Berlin, London, Madrid, New York, Paris, Rome

