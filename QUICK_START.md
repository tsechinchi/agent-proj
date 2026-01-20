# Quick Start Guide - Minimized Free API Setup

## 🚀 Get Started in 10 Minutes

### Step 1: Get Your Free API Keys (5 minutes)

#### 1.1 OpenRouter (Free LLM)
1. Go to https://openrouter.ai/
2. Click "Sign in" → Sign up with Google/GitHub
3. Go to "Keys" section
4. Click "Create Key"
5. Copy your key: `sk-or-v1-...`

**Cost**: $0/month (free models available)

---

#### 1.2 OpenWeatherMap (Free Weather)
1. Go to https://openweathermap.org/api
2. Click "Sign Up"
3. Verify your email
4. Go to API Keys section
5. Copy your default API key

**Cost**: $0/month (1000 calls/day free)

---

### Step 2: Configure Environment (2 minutes)

Copy `keys.env` to `.env` and update:

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

---

### Step 3: Install & Run (3 minutes)

```bash
# Install dependencies
pip install -e .

# Test it works
python main.py "Plan a 5-day trip to Tokyo" \
  --duration 5 \
  --interests "food, culture"
```

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

```bash
# Test 1: Basic request (uses LLM + Wikipedia)
python main.py "I want to visit Paris"

# Test 2: With weather data
python main.py "5-day Tokyo trip in July" --duration 5

# Test 3: Full parameters (flights, hotels, attractions)
python main.py "Plan my Italy vacation" \
  --origin JFK \
  --destination FCO \
  --depart 2025-07-01 \
  --return 2025-07-10 \
  --check-in 2025-07-01 \
  --check-out 2025-07-10 \
  --interests "art, food, history" \
  --duration 10
```

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

## 🔄 Upgrade to Real Data (When Needed)

### Option 1: Free Alternatives
**Skyscanner Rapid API** (Free tier)
```bash
# Add to .env
RAPIDAPI_KEY="your-free-key"
```

**Booking.com Affiliate API** (Free, commission-based)
```bash
# Add to .env
BOOKING_AFFILIATE_ID="your-affiliate-id"
```

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

For questions or issues, see [README.md](README.md) or [API_MIGRATION_SUMMARY.md](API_MIGRATION_SUMMARY.md).
