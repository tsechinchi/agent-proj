# Quick Start Guide - Minimized Free API Setup

## 🚀 Get Started 

### Step 1: Get Your Free API Keys 

#### 1.1 OpenRouter (Free LLM)
1. Go to https://openrouter.ai/
2. Click "Sign in" → Sign up with Google/GitHub
3. Go to "Keys" section
4. Click "Create Key"
5. Copy your key: `sk-or-v1-...`

---

#### 1.2 OpenWeatherMap (Free Weather)
1. Go to https://openweathermap.org/api
2. Click "Sign Up"
3. Verify your email
4. Go to API Keys section
5. Copy your default API key

---

### Step 2: Configure Environment

Update .env:

```bash
# Required (FREE)
OPENAI_API_KEY="sk-or-v1-your-openrouter-key-here"
OPENWEATHER_API_KEY="your-openweather-key-here"

# Optional (for email)
SMTP_EMAIL="your-email@gmail.com"
SMTP_PASSWORD="your-app-password"
ALLOW_AUTO_EMAIL_PDF="false"
```

**Optional (Amadeus sandbox for flights & hotels):**
```bash
# Optional: enable Amadeus sandbox for realistic flight/hotel data
AMADEUS_CLIENT_ID="your-client-id"
AMADEUS_CLIENT_SECRET="your-client-secret"
AMADEUS_ENV="test"
```

⚠️ **Amadeus Sandbox Limitations:**
- Only supports 7 cities: Barcelona, Berlin, London, Madrid, New York, Paris, Rome
- Can be unstable (500 errors, timeouts, empty results)
- When it fails, the system falls back to mock data automatically
⚠️ **PDF/Email not fixed:**
- Currently both these function don't work

---

### Step 3: Install & Run (3 minutes)

```bash
# Install dependencies
pip install uv 
uv sync

# Run the Streamlit web interface
uv run streamlit run web_api.py
```

The app will open at `http://localhost:8501` in your browser.

---

## ✅ What You Get With Free APIs

| Feature | Status | API Used |
|---------|--------|----------|
| LLM Chat | ✅ Free | OpenRouter (nvidia/nemotron-3-nano-30b-a3b:free) |
| Weather Data | ✅ Free | OpenWeatherMap (1000 calls/day) |
| Flights | ✅ Demo | Mock data (realistic) |
| Hotels | ✅ Demo | Mock data (realistic) |
| Attractions | ✅ Free | Wikipedia API (unlimited) |
| PDF Generation | ✅ Free | reportlab (local) |
| Email Sending | ⚙️ Optional | Gmail SMTP (free) |

---

## 📧 Optional: Enable Email (Gmail SMTP)

If you want to send itineraries via email:

### 1. Enable 2-Factor Authentication
1. Go to https://myaccount.google.com/security
2. Enable 2-Step Verification

### 2. Generate App Password
1. Go to https://myaccount.google.com/apppasswords
2. Select "Mail" and "Other (Custom name)"
3. Enter "Travel Agent"
4. Copy the 16-character password

### 3. Update .env
```bash
SMTP_EMAIL="your-email@gmail.com"
SMTP_PASSWORD="abcd efgh ijkl mnop"  # Your 16-char app password
SMTP_SERVER="smtp.gmail.com"
SMTP_PORT="587"
ALLOW_AUTO_EMAIL_PDF="true"
```

---

## 🧪 Test Your Setup

Once the Streamlit app is running at `http://localhost:8501`:

**💡 Destination Tips:**
- Supported cities (Amadeus sandbox): `NYC`, `PAR`, `LON`, `ROM`, `BER`, `MAD`, `BCN`
- Typos auto-correct: `NYK` → `NYC`, `LDN` → `LON`, `Roma` → `ROM`
- Other cities work with mock data

1. **Basic Request** — In the form, enter: "I want to visit Paris"
   - Click "Generate Travel Plan"
   - Should return enhanced request and itinerary

2. **With Duration** — Enter: "5-day Tokyo trip in July" with Duration = 5
   - Should generate weather-aware itinerary

3. **Full Parameters** — Fill in all fields:
   - Request: "Plan my Italy vacation"
   - Origin: JFK
   - Destination: FCO
   - Departure Date: 2025-07-01
   - Return Date: 2025-07-10
   - Check-in / Check-out: Same as departure/return
   - Interests: "art, food, history"
   - Duration: 10
   - Click "Generate Travel Plan"
   - Should trigger flights, hotels, attractions, and weather lookups

All results appear in the **Results** section with tabs for Plan, Tool Results, and Execution Notes.

---

## 🎯 What Works in Demo Mode

### ✅ Fully Functional
- AI-powered itinerary planning
- Weather forecasts
- Attraction recommendations (Wikipedia)
- PDF generation
- Email delivery (with SMTP configured)

### 📊 Demo/Mock Data
- **Flights**: Realistic mock data with carriers, times, prices
  - Example: "AA123: JFK 08:30 → FCO 14:45 - $450"
  - *For production*: Integrate Skyscanner API
  
- **Hotels**: Realistic mock data with pricing tiers
  - Example: "Grand Hotel Rome - $180/night - luxury"
  - *For production*: Integrate Booking.com API

---

### Option 2: Paid / Sandbox APIs (Amadeus)
If you want live or sandbox flight & hotel data use Amadeus credentials. The
project will continue to work without these keys (it falls back to mock data).

```bash
# Add to .env (optional)
AMADEUS_CLIENT_ID="your-client-id"
AMADEUS_CLIENT_SECRET="your-secret"
AMADEUS_ENV="test"  # or "production"
```

The code in [agents/tools/tools.py](agents/tools/tools.py) will try Amadeus when
credentials are present and otherwise return deterministic mock results.

---

## ❓ Troubleshooting

### Destination not recognized / "not available in Amadeus sandbox"
- **Amadeus sandbox only supports**: Barcelona, Berlin, London, Madrid, New York, Paris, Rome
- Use correct codes: `NYC` (not `NYK`), `LON` (not `LDN`), `PAR`, `ROM`, `BER`, `MAD`, `BCN`
- The system auto-corrects common typos: `NYK` → `NYC`, `LDN` → `LON`, `Roma` → `ROM`
- For unsupported cities, the system will use mock data automatically

### Amadeus API errors / empty results
The Amadeus sandbox can be **unstable**. Common issues:
- **500 Internal Server Error**: Sandbox is overloaded — retry later or use mock mode
- **Empty hotel/flight results**: Even for supported cities, sandbox data is limited
- **Timeout errors**: Sandbox response times can be slow

**Solutions:**
- Wait and retry — sandbox instability is often temporary
- Use mock mode for demos (unset `AMADEUS_CLIENT_ID`)
- Check Amadeus status: https://status.amadeus.com/

### "OPENAI_API_KEY not set"
- Make sure `.env` file exists
- Check key starts with `sk-or-v1-`
- Load with: `source .env` or use `python-dotenv`

### "OPENWEATHER_API_KEY not set"
- Verify email on OpenWeatherMap
- Key activation takes ~10 minutes
- Test at: `https://api.openweathermap.org/data/2.5/weather?q=London&appid=YOUR_KEY`

### "No module named 'reportlab'"
```bash
pip install reportlab
```

### "SMTP authentication failed"
- Use **app-specific password**, not your regular Gmail password
- Enable 2FA first
- Remove spaces from 16-char password

---

## 📊 Free API Limits

| API | Free Tier | Limit |
|-----|-----------|-------|
| OpenRouter | Free models | Rate limited (60 req/min) |
| OpenWeatherMap | Free tier | 1000 calls/day, 60 calls/min |
| Wikipedia | Free | Unlimited (be reasonable) |
| Gmail SMTP | Free | 500 emails/day |

**Typical Usage**: 5-10 API calls per itinerary request
- 2-4 LLM calls (OpenRouter)
- 1-2 weather calls (OpenWeatherMap)
- 1-2 attraction searches (Wikipedia)

**Daily Capacity**: ~100-200 itineraries/day (well within free limits)

---

## 🎉 You're Ready!

Your minimalist travel planning system is now configured with:
- ✅ $0/month cost
- ✅ 2 free API keys
- ✅ Full AI-powered planning
- ✅ No complex OAuth or service accounts

Start planning trips:
```bash
python main.py "Where should I go for a week in summer?"
```
