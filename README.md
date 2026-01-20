# agent-proj

Multi-agent travel planning system with observability, deployment, and evaluation capabilities.

## 🚀 Quick Start

**New user?** See [QUICK_START.md](QUICK_START.md) for 10-minute setup guide.

**Want details?** See [API_COMPARISON.md](API_COMPARISON.md) for full provider comparison.

**Migrating?** See [API_MIGRATION_SUMMARY.md](API_MIGRATION_SUMMARY.md) for migration details.

---

## Features

### 🤖 Multi-Agent System
- **Request Enhancement Agent**: Clarifies and structures user travel requests
- **Planning Agent**: Creates detailed, actionable itineraries
- **Research Agent**: Gathers real-time travel data and recommendations
- **Logistics Agent**: Handles PDF generation and email delivery
- **✨ FREE APIs Only**: No paid subscriptions required for core functionality

### 🆓 Minimal API Requirements
**Only 1–2 free API keys are recommended:**
1. **OpenRouter** - Free LLM access (nvidia/nemotron-3-nano-30b-a3b:free)
2. **OpenWeatherMap** - Free weather data (1000 calls/day) — optional, the project will
     fall back to a deterministic mock weather response when `OPENWEATHER_API_KEY` is not set.

**Optional / Paid (not required to run):**
- Amadeus, Bright Data — production integrations only; the project uses mock data or
    free alternatives by default.

**What's Free / Mocked by Default:**
- ✅ Flights: Mock data (demo mode)
- ✅ Hotels: Mock data (demo mode)
- ✅ Attractions: Wikipedia API (completely free, no key)
- ✅ Weather: OpenWeatherMap free tier (or deterministic mock when unset)
- ✅ LLM: OpenRouter free models (LLMs fallback to mock when `OPENAI_API_KEY` is unset)

### 📊 Phoenix Observability
Real-time tracing and monitoring of agent execution:

**Setup Phoenix:**
```bash
pip install arize-phoenix opentelemetry-api opentelemetry-sdk
export ENABLE_PHOENIX_TRACING=true
python main.py "Your trip request"
```

**Access Phoenix Dashboard:**
### 📊 Phoenix Observability (Optional)
Real-time tracing and monitoring of agent execution. Tracing is fully optional — the
project is designed to run without Phoenix installed. When enabled you get:
- Agent call tracking with input/output logging
- Tool execution tracing with performance metrics
- LLM call instrumentation (model, tokens, latency)
- State transition tracking
- Error and exception logging
- Comprehensive trace export to JSON

Setup (optional):

- Install the Arize Phoenix package and OpenTelemetry extras if you want the
    observability dashboard locally or in Docker:

```bash
pip install arize-phoenix opentelemetry-api opentelemetry-sdk
```

- Enable tracing via environment (the code uses a lazy import so Phoenix is
    not required at import time):

```bash
export ENABLE_PHOENIX_TRACING=true
export PHOENIX_ENDPOINT="http://localhost:6006"  # or your Phoenix URL
python main.py "Your trip request"
```

Access the dashboard:

- If running the packaged app: visit `http://localhost:6006` (or the value of `PHOENIX_ENDPOINT`).
- Or launch directly from the installed Phoenix package:

```bash
python -c "import phoenix as px; px.launch_app(port=6006)"
```

Notes:
- Tracing is guarded by a lazy import; the app runs normally when `arize-phoenix`
    is not installed. Enable `ENABLE_PHOENIX_TRACING=true` only when you have the
    dependency or a running Phoenix server.

### 🚀 ONNX Runtime Deployment
Deployment utilities use ONNX Runtime for inference and model optimization.
This repository provides a small `Deployer` interface that can operate in
mock mode when `onnxruntime` is not installed, allowing development without
native runtime dependencies.

Features:
- Multiple deployment strategies (local, Docker, Kubernetes, cloud, edge)
- Model optimization hints and integration points for ONNX tooling
- Multi-device deployment (CPU/GPU) and quantization support
- Batch size and sequence length tuning

**Example Deployment:**
```python
from deployment.deployer import Deployer, DeploymentStrategy, get_recommended_config

# Get recommended config for your setup
config = get_recommended_config(
    strategy=DeploymentStrategy.KUBERNETES,
    num_gpus=4
)

# Deploy with optimization (ONNX Runtime)
deployer = Deployer(config)
deployer.optimize_model("travel-planner-v1", "./models/travel_planner")
deployer.deploy(
    model_name="travel-planner-v1",
    model_path="./models/travel_planner"
)
```

**Deployment Strategies:**
- **LOCAL**: Single machine with optional GPU (fp16)
- **DOCKER**: Containerized deployment with resource limits
- **KUBERNETES**: Distributed multi-GPU/multi-node cluster
- **CLOUD**: Managed cloud service (AWS/GCP/Azure)
- **EDGE**: Optimized for edge devices (int8, minimal memory)

### 📈 Evaluation Framework
Comprehensive evaluation of multi-agent system performance:

**Execution Metrics:**
- Agent invocation and success rates
- Tool call effectiveness
- LLM call tracking
- Execution time and duration
- Error tracking and categorization

**Quality Scoring:**
- Completeness (0-100): Coverage of all request areas
- Relevance (0-100): Alignment with user intent
- Coherence (0-100): Logical flow and structure
- Practicality (0-100): Feasibility of the plan
- Detail Level (0-100): Specificity and depth

**Tool Performance:**
- Per-tool effectiveness scores
- Success rate tracking
- Error categorization
- Result quality assessment

**Example Evaluation:**
```python
from evaluation import get_evaluator
import time

evaluator = get_evaluator()

# Track execution
start_time = time.time()
result = app.invoke(state)
duration = time.time() - start_time

# Evaluate
metrics = evaluator.evaluate_execution(
    initial_state=state,
    final_state=result,
    execution_time=duration,
    agent_trace=["enhance", "plan", "fetch_inventory"],
    errors=[]
)

quality = evaluator.evaluate_quality(
    request=state["request"],
    plan=result["plan"],
    provided_structured_data=bool(state.get("origin"))
)

# Generate comprehensive report
report = evaluator.get_report()
evaluator.save_report("evaluation_report.json")
```

## Architecture

```
agent-proj/
├── agents/                 # Multi-agent system
│   ├── agents.py          # LLM configuration and prompts
│   └── tools/             # Agent tools
│       └── tools.py       # Travel search & logistics tools
├── observability/          # Phoenix tracing integration
│   ├── __init__.py
│   └── phoenix_tracer.py  # Observability wrapper
├── evaluation/            # System evaluation framework
│   ├── __init__.py
│   └── evaluator.py       # Metrics and quality scoring
├── deployment/            # Deployment configuration
│   ├── __init__.py
│   └── deployer.py        # ONNX Runtime model optimization & deployment
├── main.py               # CLI entry point
├── stategraph.py         # LangGraph state machine
├── pytest.py             # Test suite
├── pyproject.toml        # Dependencies and metadata
└── README.md             # This file
```

## Installation

```bash
# Clone repository
git clone <repo-url>
cd agent-proj

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Optional: Install evaluation/observability extras
pip install arize-phoenix opentelemetry-api opentelemetry-sdk
```

## Configuration

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

Notes:
- If `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` are not set the code will
    fall back to deterministic mock flight/hotel results for local development.
- The code accepts common alternate env names for backwards compatibility, but
    prefer `AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET`.
```

#### 3. Optional: Email via Gmail SMTP
For PDF delivery (optional):
1. Enable 2FA on Gmail
2. Generate app password at https://myaccount.google.com/apppasswords
```bash
export SMTP_EMAIL="your-email@gmail.com"
export SMTP_PASSWORD="your-app-specific-password"
export ALLOW_AUTO_EMAIL_PDF="true"
```

### Environment Variables

Create a `keys.env` file (copy from template):

```env
# Required: LLM (Free)
OPENAI_API_KEY="sk-or-v1-your-openrouter-key"

# Required: Weather (Free - 1000 calls/day)
OPENWEATHER_API_KEY="your-openweather-key"

# Optional: Email notifications
SMTP_EMAIL="your-email@gmail.com"
SMTP_PASSWORD="your-app-specific-password"
ALLOW_AUTO_EMAIL_PDF="false"

# Optional: Phoenix Observability
ENABLE_PHOENIX_TRACING="true"
PHOENIX_ENDPOINT="http://localhost:6006"

# Optional: Deployment settings
DEPLOYMENT_STRATEGY="local"  # local, docker, kubernetes, cloud, edge
DEPLOYMENT_OPTIMIZATION_LEVEL="moderate"  # none, light, moderate, aggressive
```

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

### With Full Observability

```bash
export ENABLE_PHOENIX_TRACING=true
python main.py "Plan my Italy trip" \
  --origin JFK --destination FCO --depart 2025-07-01 --return 2025-07-10 \
  --interests "art, culture, food"
```

### Evaluate System Performance

```python
from main import travel_graph, TravelState
from evaluation import get_evaluator
import time

evaluator = get_evaluator()
state = TravelState(request="5-day Paris trip", duration=5)

start = time.time()
result = travel_graph.invoke(state)
duration = time.time() - start

# Evaluate execution and quality
metrics = evaluator.evaluate_execution(
    initial_state=state,
    final_state=result,
    execution_time=duration,
)

quality = evaluator.evaluate_quality(
    request=state["request"],
    plan=result["plan"],
)

print(f"Success Rate: {metrics.success_rate():.1%}")
print(f"Quality Score: {quality.overall_score():.1f}/100")

evaluator.save_report()
```

### Deploy with ONNX Runtime

```python
from deployment.deployer import Deployer, get_recommended_config, DeploymentStrategy

# Get recommended config for Kubernetes deployment
config = get_recommended_config(
    strategy=DeploymentStrategy.KUBERNETES,
    num_gpus=4
)

deployer = Deployer(config)

# Optimize models (mocked if onnxruntime not available)
deployer.optimize_model("nemotron-3-nano-30b", "./models/nemotron-3-nano-30b", optimization_level=None)

# Deploy
deployment = deployer.deploy(
    model_name="travel-planner",
    model_path="./models/travel_planner",
    service_name="travel-planner-api"
)

# Inspect deployment status and save config
print(deployer.deployment_status)
deployer.config.to_json("deployment_config.json")
```

## Metrics & Monitoring

### Execution Metrics Tracked

- ✅ Agent success rates
- ✅ Tool invocation and success rates  
- ✅ LLM call count and token usage
- ✅ Execution duration
- ✅ Error tracking and categorization
- ✅ State transition tracking

### Quality Metrics Tracked

- ✅ Itinerary completeness
- ✅ Relevance to user request
- ✅ Coherence and structure
- ✅ Practicality and feasibility
- ✅ Detail level and specificity
- ✅ Overall weighted score (0-100)

## Testing

```bash
# Run tests
python pytest.py

# Run with coverage
pytest pytest.py --cov=agents --cov=observability --cov=evaluation --cov=deployment
```

## Performance Tuning

### For Production Deployments

1. **Enable Quantization**: Use int8 for edge, fp16 for cloud
2. **Batch Processing**: Increase batch size for throughput
3. **Caching**: Enable response caching for similar queries
4. **Monitoring**: Use Phoenix observability in production
5. **Evaluation**: Regular evaluation reports for quality assurance

### Memory Optimization

- Use Flash Attention (30-40% memory reduction)
- Enable gradient checkpointing for training
- Implement dynamic batching
- Use mixed precision (fp16/fp32)

### Latency Optimization

- Tensor parallelism for multi-GPU
- Model quantization (int8)
- KV cache optimization
- Speculative decoding

## Troubleshooting

### Phoenix Not Connecting

```bash
# Check endpoint
export PHOENIX_ENDPOINT=http://localhost:6006
# Launch Phoenix explicitly
python -c "import phoenix as px; px.launch_app(port=6006)"
```

### Deployment Troubleshooting

```bash
# Verify ONNX Runtime installation
python -c "import onnxruntime as ort; print(getattr(ort, '__version__', 'not-installed'))"
# Check GPU availability (PyTorch)
python -c "import torch; print(torch.cuda.is_available())"
```

### Evaluation Metrics Not Recording

```python
# Check evaluator is initialized
from evaluation import get_evaluator
evaluator = get_evaluator()
print(evaluator.get_report())
```

## License

See LICENSE file for details.

## Support

For issues and questions:
- Check [Phoenix Docs](https://docs.arize.com/phoenix)
- See [LangGraph Documentation](https://langchain-ai.github.io/langgraph)