"""LangGraph travel planning flow with two-phase planning, autonomous tool selection, and human-in-the-loop.

Architecture:
1. enhance_request: Clarify user needs
2. draft_plan: Create initial itinerary outline (without tool data)
3. decide_tools: LLM autonomously decides which tools to run
4. run_tools: Execute selected tools sequentially
5. refine_plan: Merge tool data into enriched itinerary
6. human_review: Pause for user approval/feedback
7. [if modifications] → loop back to refine_plan (up to MAX_ITERATIONS)
8. finalize: Prepare final outputs
9. END

Conversation context is maintained across all LLM calls via messages list.
Tool results are structured and integrated into refined plan.
Supports both CLI and Streamlit execution modes.
"""

import logging
from typing import TypedDict, Optional, Any, Literal
import json

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

from agents.agents import (
    build_planner_agent,
    build_refiner_agent,
    build_tool_selector_agent,
    is_mock_mode,
)
from agents.tools.tools import (
    find_flights,
    find_hotels,
    attraction_finder,
    weather_checker,
)

logger = logging.getLogger(__name__)

# Configuration
MAX_ITERATIONS = 5  # Maximum refinement loops to prevent infinite cycling


class TravelState(TypedDict, total=False):
    """Comprehensive state schema for travel planning with multi-turn conversation support.
    
    State flows through these phases:
    1. Input phase: User provides request and optional structured data
    2. Planning phase: Draft → Tools → Refine
    3. Review phase: Human approval/feedback loop
    4. Finalization: Prepare outputs
    """
    
    # User input
    request: str  # Natural language request
    origin: Optional[str]  # Departure city/code
    destination: Optional[str]  # Destination city/code
    depart_date: Optional[str]  # YYYY-MM-DD
    return_date: Optional[str]  # YYYY-MM-DD (optional)
    check_in: Optional[str]  # Hotel check-in YYYY-MM-DD
    check_out: Optional[str]  # Hotel check-out YYYY-MM-DD
    interests: Optional[str]  # Comma-separated interests
    duration: int  # Trip length in days
    
    # Conversation history (maintained across LLM calls)
    messages: list[BaseMessage]  # Full conversation context
    
    # Planning state (two-phase approach)
    draft_plan: str  # Initial itinerary (before tool data)
    plan: str  # Final refined itinerary
    
    # Tool execution state
    selected_tools: list[str]  # Tools LLM decided to run (autonomous decision)
    tool_results: dict[str, Any]  # Structured tool outputs: {tool_name: data}
    
    # Human review state
    human_feedback: Optional[str]  # User modifications/feedback
    approved: bool  # User approval status
    awaiting_review: bool  # Flag indicating graph is paused for human input
    iteration_count: int  # Loop counter (prevents infinite loops)
    
    # Execution mode
    execution_mode: str  # "cli" or "streamlit" - affects how human_review behaves
    
    # Metadata
    notes: list[str]  # Execution log


def _ensure_messages(state: TravelState) -> list[BaseMessage]:
    """Initialize messages list if absent."""
    if "messages" not in state or state["messages"] is None:
        return []
    return state["messages"]


def enhance_request(state: TravelState) -> TravelState:
    """Clarify user needs using planning agent."""
    user_req = state.get("request", "")
    if not user_req.strip():
        return {**state, "notes": ["request missing"], "draft_plan": "", "plan": ""}
    
    messages = _ensure_messages(state)
    
    try:
        # Use planning agent to enhance request
        agent = build_planner_agent()
        enhance_prompt = (
            f"Clarify and enhance this travel request. Provide 3 bullet points:\n"
            f"• Goals: What does the traveler want to accomplish?\n"
            f"• Constraints: Budget, time, visa, mobility, etc.\n"
            f"• Preferences: Climate, accommodation style, pace, etc.\n\n"
            f"Request: {user_req}"
        )
        messages_with_input = messages + [HumanMessage(content=enhance_prompt)]
        response = agent.invoke({"messages": messages_with_input, "input": enhance_prompt})
        
        text = response.content if hasattr(response, "content") else str(response)
        messages_with_input.append(AIMessage(content=text))
        
        logger.info("Request enhanced successfully")
    except Exception as e:
        logger.warning(f"Error enhancing request (fallback): {type(e).__name__}: {e}")
        text = f"Mock: Clarified travel request\n• Goals: Explore destination\n• Constraints: Standard\n• Preferences: Flexible"
        messages_with_input = messages + [HumanMessage(content=user_req), AIMessage(content=text)]
    
    notes = state.get("notes", []) or []
    notes.append("request enhanced")
    
    return {
        **state,
        "draft_plan": text,
        "messages": messages_with_input,
        "notes": notes,
    }


def draft_plan(state: TravelState) -> TravelState:
    """Create initial itinerary outline WITHOUT tool data (phase 1 of 2)."""
    messages = _ensure_messages(state)
    duration = state.get("duration", 3)
    context = state.get("draft_plan", state.get("request", ""))
    
    try:
        agent = build_planner_agent()
        prompt = (
            f"Create a {duration}-day travel itinerary outline for a traveler with these goals:\n{context}\n\n"
            f"Destination: {state.get('destination', 'Unknown')}\n"
            f"Depart: {state.get('depart_date', 'TBD')}\n"
            f"Return: {state.get('return_date', 'TBD')}\n\n"
            f"Provide day-by-day outline (actual flight/hotel data will be added later).\n"
            f"Format as numbered days with activities."
        )
        messages_with_input = messages + [HumanMessage(content=prompt)]
        response = agent.invoke({"messages": messages_with_input, "input": prompt})
        
        text = response.content if hasattr(response, "content") else str(response)
        messages_with_input.append(AIMessage(content=text))
        
        logger.info(f"Draft plan created for {duration}-day trip")
    except Exception as e:
        logger.warning(f"Error creating draft plan (fallback): {type(e).__name__}: {e}")
        text = f"Day-by-Day Outline ({duration} days):\n• Day 1: Arrival\n• Days 2-{duration-1}: Exploration\n• Day {duration}: Departure"
        messages_with_input = messages + [HumanMessage(content="create draft plan"), AIMessage(content=text)]
    
    notes = state.get("notes", []) or []
    notes.append(f"draft {duration}-day plan created")
    
    return {
        **state,
        "draft_plan": text,
        "messages": messages_with_input,
        "notes": notes,
    }


def decide_tools(state: TravelState) -> TravelState:
    """LLM autonomously decides which tools to invoke (autonomous agent decision)."""
    messages = _ensure_messages(state)
    has_flights = state.get("origin") and state.get("destination") and state.get("depart_date")
    has_hotels = state.get("destination") and state.get("check_in") and state.get("check_out")
    has_dest = state.get("destination")
    
    try:
        agent = build_tool_selector_agent()
        prompt = (
            f"Based on this travel request, decide which tools to call.\n"
            f"Available tools: find_flights, find_hotels, attraction_finder, weather_checker\n\n"
            f"Available data:\n"
            f"- Flights: {'yes (origin, dest, date provided)' if has_flights else 'no (missing data)'}\n"
            f"- Hotels: {'yes (dest, check-in/out provided)' if has_hotels else 'no (missing data)'}\n"
            f"- Attractions: {'yes (destination provided)' if has_dest else 'no (missing data)'}\n"
            f"- Weather: {'yes (destination provided)' if has_dest else 'no (missing data)'}\n\n"
            f"Context: {state.get('draft_plan', '')}\n\n"
            f"Output JSON list of tools to call: ['find_flights', 'find_hotels', 'attraction_finder', 'weather_checker']\n"
            f"Only include tools where data is available."
        )
        messages_with_input = messages + [HumanMessage(content=prompt)]
        response = agent.invoke({"messages": messages_with_input, "input": prompt})
        
        response_text = response.content if hasattr(response, "content") else str(response)
        messages_with_input.append(AIMessage(content=response_text))
        
        # Parse JSON list from response
        try:
            # Find JSON array in response
            start_idx = response_text.find("[")
            end_idx = response_text.rfind("]") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                selected = json.loads(json_str)
            else:
                selected = []
        except json.JSONDecodeError:
            selected = []
        
        logger.info(f"Tool selector decided to run: {selected}")
    except Exception as e:
        logger.warning(f"Error in tool selection (fallback): {type(e).__name__}: {e}")
        # Fallback: select tools based on available data
        selected = []
        if has_flights:
            selected.append("find_flights")
        if has_hotels:
            selected.append("find_hotels")
        if has_dest:
            selected.extend(["attraction_finder", "weather_checker"])
        messages_with_input = messages + [
            HumanMessage(content="decide which tools to call"),
            AIMessage(content=f"Selected tools: {selected}")
        ]
    
    notes = state.get("notes", []) or []
    notes.append(f"tool selection: {selected}")
    
    return {
        **state,
        "selected_tools": selected,
        "messages": messages_with_input,
        "notes": notes,
    }


def run_tools(state: TravelState) -> TravelState:
    """Execute selected tools sequentially and structure results."""
    selected_tools = state.get("selected_tools", [])
    tool_results = {}
    notes = state.get("notes", []) or []
    
    # Sequential tool execution (no parallelization)
    if "find_flights" in selected_tools:
        origin = state.get("origin")
        destination = state.get("destination")
        depart = state.get("depart_date")
        if origin and destination and depart:
            try:
                resp = find_flights.invoke({
                    "origin": origin,
                    "destination": destination,
                    "depart_date": depart,
                    "return_date": state.get("return_date"),
                })
                tool_results["flights"] = str(resp)
                logger.info("find_flights executed")
                if "mock" in str(resp).lower():
                    notes.append("flights: mock data")
                else:
                    notes.append("flights: live data")
            except Exception as e:
                logger.exception("find_flights failed")
                tool_results["flights"] = f"Error: {e}"
                notes.append(f"flights: error - {e}")
        else:
            notes.append("flights: skipped (missing origin/destination/depart_date)")
    
    if "find_hotels" in selected_tools:
        destination = state.get("destination")
        check_in = state.get("check_in")
        check_out = state.get("check_out")
        if destination and check_in and check_out:
            try:
                resp = find_hotels.invoke({
                    "destination": destination,
                    "check_in": check_in,
                    "check_out": check_out,
                })
                tool_results["hotels"] = str(resp)
                logger.info("find_hotels executed")
                if "mock" in str(resp).lower():
                    notes.append("hotels: mock data")
                else:
                    notes.append("hotels: live data")
            except Exception as e:
                logger.exception("find_hotels failed")
                tool_results["hotels"] = f"Error: {e}"
                notes.append(f"hotels: error - {e}")
        else:
            notes.append("hotels: skipped (missing destination/check_in/check_out)")
    
    if "attraction_finder" in selected_tools:
        destination = state.get("destination")
        if destination:
            try:
                resp = attraction_finder.invoke({
                    "destination": destination,
                    "interests": state.get("interests"),
                })
                tool_results["attractions"] = str(resp)
                logger.info("attraction_finder executed")
                if "mock" in str(resp).lower():
                    notes.append("attractions: mock data")
                else:
                    notes.append("attractions: live data")
            except Exception as e:
                logger.exception("attraction_finder failed")
                tool_results["attractions"] = f"Error: {e}"
                notes.append(f"attractions: error - {e}")
        else:
            notes.append("attractions: skipped (missing destination)")
    
    if "weather_checker" in selected_tools:
        destination = state.get("destination")
        if destination:
            try:
                resp = weather_checker.invoke({
                    "destination": destination,
                    "date": state.get("depart_date"),
                })
                tool_results["weather"] = str(resp)
                logger.info("weather_checker executed")
                if "mock" in str(resp).lower():
                    notes.append("weather: mock data")
                else:
                    notes.append("weather: live data")
            except Exception as e:
                logger.exception("weather_checker failed")
                tool_results["weather"] = f"Error: {e}"
                notes.append(f"weather: error - {e}")
        else:
            notes.append("weather: skipped (missing destination)")
    
    notes.append("tools executed sequentially")
    
    return {
        **state,
        "tool_results": tool_results,
        "notes": notes,
    }


def refine_plan(state: TravelState) -> TravelState:
    """Merge tool data into draft plan to create refined itinerary (phase 2 of 2)."""
    messages = _ensure_messages(state)
    draft = state.get("draft_plan", "")
    tool_results = state.get("tool_results", {})
    human_feedback = state.get("human_feedback")
    duration = state.get("duration", 3)
    destination = state.get("destination", "your destination")
    
    # Build tool summary for context
    tool_context = ""
    tool_summaries = {}
    if tool_results:
        tool_context = "Real data available:\n"
        for tool_name, data in tool_results.items():
            if data and not str(data).startswith("Error"):
                tool_context += f"\n{tool_name.upper()}:\n{data[:500]}\n"
                tool_summaries[tool_name] = data[:300]
    
    try:
        agent = build_refiner_agent()
        if human_feedback:
            prompt = (
                f"User feedback on the itinerary: '{human_feedback}'\n\n"
                f"Refine the itinerary incorporating this feedback and real data.\n\n"
                f"Original draft:\n{draft}\n\n"
                f"{tool_context}\n\n"
                f"Create a detailed final itinerary with actual prices, times, and booking info where available."
            )
        else:
            prompt = (
                f"Enhance this draft itinerary with real data:\n{draft}\n\n"
                f"{tool_context}\n\n"
                f"Create a detailed final itinerary with actual prices, times, and hotel/flight recommendations."
            )
        
        messages_with_input = messages + [HumanMessage(content=prompt)]
        response = agent.invoke({"messages": messages_with_input, "input": prompt})
        
        refined_text = response.content if hasattr(response, "content") else str(response)
        messages_with_input.append(AIMessage(content=refined_text))
        
        logger.info("Plan refined with tool data")
    except Exception as e:
        logger.warning(f"Error refining plan (fallback): {type(e).__name__}: {e}")
        # Generate a more useful fallback that includes tool data
        refined_text = _generate_fallback_itinerary(
            draft=draft,
            tool_data=tool_summaries,
            duration=duration,
            destination=destination,
            feedback=human_feedback
        )
        messages_with_input = messages + [
            HumanMessage(content="refine plan with tool data"),
            AIMessage(content=refined_text)
        ]
    
    notes = state.get("notes", []) or []
    notes.append("plan refined with tool results")
    
    return {
        **state,
        "plan": refined_text,
        "messages": messages_with_input,
        "approved": False,  # Still awaiting approval after refinement
        "human_feedback": None,  # Clear feedback after processing
        "notes": notes,
    }


def _generate_fallback_itinerary(draft: str, tool_data: dict, duration: int, destination: Optional[str], feedback: Optional[str] = None) -> str:
    """Generate a reasonable itinerary when LLM is unavailable, incorporating tool data.
    
    Provides explicit messaging about partial results and data sources.
    """
    dest_name = destination or "your destination"
    lines = [f"# {duration}-Day Trip to {dest_name}\n"]
    
    # Track data source status for transparency
    data_sources = []
    partial_results = False
    
    if feedback:
        lines.append(f"*Note: Incorporating feedback: {feedback}*\n")
    
    # Add hotel info if available
    if "hotels" in tool_data:
        hotel_data = tool_data["hotels"]
        lines.append("## 🏨 Accommodation")
        # Check if this is partial/fallback data
        if "PARTIAL RESULTS" in hotel_data or "mock" in hotel_data.lower() or "demo" in hotel_data.lower():
            partial_results = True
            data_sources.append("🏨 Hotels: ⚠️ Partial/fallback data")
        else:
            data_sources.append("🏨 Hotels: ✅ Live data")
        lines.append(hotel_data[:400])
        lines.append("")
    
    # Add weather info if available
    if "weather" in tool_data:
        weather_data = tool_data["weather"]
        lines.append("## 🌤️ Weather Forecast")
        if "error:" in weather_data.lower() or "mock" in weather_data.lower():
            partial_results = True
            data_sources.append("🌤️ Weather: ⚠️ Unavailable or estimated")
        else:
            data_sources.append("🌤️ Weather: ✅ Live data")
        lines.append(weather_data[:300])
        lines.append("")
    
    # Add attraction info if available
    if "attractions" in tool_data:
        attraction_data = tool_data["attractions"]
        lines.append("## 🎭 Attractions & Activities")
        if "PARTIAL RESULTS" in attraction_data or "suggested attractions" in attraction_data.lower():
            partial_results = True
            data_sources.append("🎭 Attractions: ⚠️ General recommendations")
        else:
            data_sources.append("🎭 Attractions: ✅ Live data")
        lines.append(attraction_data[:400])
        lines.append("")
    
    # Add flight info if available
    if "flights" in tool_data:
        flight_data = tool_data["flights"]
        lines.append("## ✈️ Flight Options")
        if "mock" in flight_data.lower() or "demo" in flight_data.lower():
            partial_results = True
            data_sources.append("✈️ Flights: ⚠️ Demo/sample data")
        else:
            data_sources.append("✈️ Flights: ✅ Live data")
        lines.append(flight_data[:400])
        lines.append("")
    
    # Add day-by-day outline
    lines.append("## 📅 Day-by-Day Outline")
    for day in range(1, duration + 1):
        if day == 1:
            lines.append(f"\n**Day {day}: Arrival**")
            lines.append("- Arrive at destination")
            lines.append("- Check in to hotel")
            lines.append("- Evening exploration of local area")
        elif day == duration:
            lines.append(f"\n**Day {day}: Departure**")
            lines.append("- Morning leisure time")
            lines.append("- Check out and depart")
        else:
            lines.append(f"\n**Day {day}: Exploration**")
            lines.append("- Morning: Cultural attractions")
            lines.append("- Afternoon: Leisure & shopping")
            lines.append("- Evening: Local dining")
    
    lines.append("\n---")
    
    # Explicit data source summary
    lines.append("\n### 📊 Data Sources")
    for source in data_sources:
        lines.append(f"- {source}")
    
    # Clear messaging about what happened
    if partial_results:
        lines.append("\n⚠️ **PARTIAL RESULTS NOTICE**")
        lines.append("Some data sources returned incomplete or fallback information due to:")
        lines.append("- API rate limits or temporary unavailability")
        lines.append("- Dates outside forecast range (weather)")
        lines.append("- No availability for requested dates (hotels)")
        lines.append("\n*For complete planning, try again later or adjust your dates.*")
    else:
        lines.append("\n*Note: LLM refinement was unavailable. This outline uses live tool data where possible.*")
    
    return "\n".join(lines)


def human_review(state: TravelState) -> TravelState:
    """Mark state as awaiting human review.
    
    This node sets awaiting_review=True and returns immediately.
    The actual human interaction happens outside the graph:
    - CLI mode: main.py handles input() calls
    - Streamlit mode: web_api.py handles session state and forms
    
    After human provides feedback, the caller updates state and either:
    - Continues to finalize (if approved)
    - Re-invokes refine_plan (if modifications requested)
    """
    notes = state.get("notes", []) or []
    iteration = state.get("iteration_count", 0)
    
    notes.append(f"awaiting human review (iteration {iteration + 1}/{MAX_ITERATIONS})")
    logger.info(f"Graph paused for human review (iteration {iteration + 1})")
    
    return {
        **state,
        "awaiting_review": True,
        "notes": notes,
    }


def route_after_review(state: TravelState) -> Literal["finalize", "refine", "end"]:
    """Route based on human approval status and iteration count.
    
    Returns:
    - "finalize": User approved, proceed to finalization
    - "refine": User requested modifications, loop back
    - "end": Max iterations reached or still awaiting review
    """
    approved = state.get("approved", False)
    awaiting = state.get("awaiting_review", False)
    iteration = state.get("iteration_count", 0)
    feedback = state.get("human_feedback")
    
    # If still awaiting review, exit graph (will be re-entered after human input)
    if awaiting:
        logger.info("Graph exiting: awaiting human review")
        return "end"
    
    # If approved, proceed to finalization
    if approved:
        logger.info("Routing to finalize: user approved")
        return "finalize"
    
    # If modifications requested and under iteration limit, refine again
    if feedback and iteration < MAX_ITERATIONS:
        logger.info(f"Routing to refine: user feedback received (iteration {iteration})")
        return "refine"
    
    # Max iterations reached or no feedback
    if iteration >= MAX_ITERATIONS:
        logger.warning(f"Max iterations ({MAX_ITERATIONS}) reached, finalizing anyway")
        return "finalize"
    
    # Default: exit graph
    logger.info("Graph exiting: no clear routing decision")
    return "end"


def finalize(state: TravelState) -> TravelState:
    """Prepare final outputs and mark completion.
    
    This node:
    - Ensures plan is set (copies from draft if needed)
    - Clears awaiting_review flag
    - Adds finalization note
    """
    notes = state.get("notes", []) or []
    plan = state.get("plan", "")
    draft = state.get("draft_plan", "")
    
    # Ensure we have a final plan
    if not plan and draft:
        plan = draft
    
    notes.append("itinerary finalized")
    logger.info("Itinerary finalized successfully")
    
    return {
        **state,
        "plan": plan,
        "awaiting_review": False,
        "approved": True,
        "notes": notes,
    }


def build_graph():
    """Construct the LangGraph state machine with refinement loop support.
    
    Graph Flow:
    START → enhance → draft → decide_tools → run_tools → refine → human_review
                                                            ↑            ↓
                                                            └── [feedback] ──┘
                                                                         ↓
                                                            [approved] → finalize → END
    
    The human_review node pauses execution. When the caller provides feedback:
    - If approved: route to finalize
    - If modifications: route back to refine
    - If max iterations: route to finalize anyway
    """
    graph = StateGraph(TravelState)
    
    # Add all nodes
    graph.add_node("enhance", enhance_request)
    graph.add_node("draft", draft_plan)
    graph.add_node("decide_tools", decide_tools)
    graph.add_node("run_tools", run_tools)
    graph.add_node("refine", refine_plan)
    graph.add_node("human_review", human_review)
    graph.add_node("finalize", finalize)
    
    # Set entry point
    graph.set_entry_point("enhance")
    
    # Linear flow for main path
    graph.add_edge("enhance", "draft")
    graph.add_edge("draft", "decide_tools")
    graph.add_edge("decide_tools", "run_tools")
    graph.add_edge("run_tools", "refine")
    graph.add_edge("refine", "human_review")
    
    # Conditional edges from human review
    # Supports three outcomes: finalize, refine (loop back), or end (pause)
    graph.add_conditional_edges(
        "human_review",
        route_after_review,
        {
            "finalize": "finalize",
            "refine": "refine",  # Loop back for refinement
            "end": END,
        }
    )
    
    graph.add_edge("finalize", END)
    
    return graph.compile()


# Compile the graph once at module load
travel_graph = build_graph()


# --- Utility functions for external callers ---

def run_until_human_review(state: TravelState) -> TravelState:
    """Run graph until it reaches human_review and pauses.
    
    This is the primary entry point for both CLI and Streamlit.
    Returns state with awaiting_review=True when paused for input.
    """
    result = travel_graph.invoke(state)
    # Cast to TravelState since we know the graph returns compatible dict
    return dict(result)  # type: ignore[return-value]


def continue_after_feedback(state: TravelState) -> TravelState:
    """Continue graph execution after human provides feedback.
    
    The caller should have already updated state with:
    - approved=True (if approving) OR
    - approved=False + human_feedback="..." (if requesting changes)
    - awaiting_review=False
    - iteration_count incremented
    
    Returns the updated state after processing.
    """
    # If approved, just finalize
    if state.get("approved"):
        result = finalize(state)
        return dict(result)  # type: ignore[return-value]
    
    # If feedback provided, refine and then pause again for review
    if state.get("human_feedback"):
        # Clear awaiting flag
        updated_state: TravelState = {**state, "awaiting_review": False}  # type: ignore[typeddict-item]
        # Run refine and human_review
        updated_state = refine_plan(updated_state)
        updated_state = human_review(updated_state)
        return updated_state
    
    # No clear action, return current state
    return state


def get_current_plan(state: TravelState) -> str:
    """Get the best available plan from state."""
    return state.get("plan") or state.get("draft_plan") or "No plan available"


def format_tool_results_for_display(tool_results: dict) -> str:
    """Format tool results for human-readable display."""
    if not tool_results:
        return "No tool data available."
    
    lines = []
    for tool_name, data in tool_results.items():
        if data and not str(data).startswith("Error"):
            lines.append(f"\n=== {tool_name.upper()} ===")
            # Truncate long results
            data_str = str(data)
            if len(data_str) > 500:
                data_str = data_str[:500] + "..."
            lines.append(data_str)
    
    return "\n".join(lines) if lines else "No usable tool data."
