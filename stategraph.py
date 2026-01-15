"""Minimal LangGraph flow for travel planning.

This keeps things simple: enhance the request, draft a plan, then optionally
hit tools if the caller provided structured trip fields. When keys are
missing, models are mocked (see agents.agents.build_llm) and tools are skipped.
"""

import logging
from typing import Annotated, TypedDict, Optional, Literal
import os

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from agents.agents import prompt_enhance_model, detail_plan_model, prompt_enhance_sys_pmt, detail_plan_sys_pmt
from agents.tools.tools import find_flights, find_hotels, attraction_finder, weather_checker

logger = logging.getLogger(__name__)


class TravelState(TypedDict, total=False):
    request: str
    origin: str
    destination: str
    depart_date: str
    return_date: Optional[str]
    check_in: Optional[str]
    check_out: Optional[str]
    interests: Optional[str]
    duration: Optional[int]
    notes: list[str]
    plan: str
    inventory: list[str]
    requires_human_approval: Optional[bool]
    tool_calls_needed: Optional[bool]


def _text_from_model(resp) -> str:
    """Handle ChatOpenAI vs mock outputs."""
    if hasattr(resp, "content"):
        return resp.content if isinstance(resp.content, str) else str(resp.content)
    return str(resp)


def enhance_request(state: TravelState) -> TravelState:
    user_req = state.get("request", "")
    if not user_req:
        return {**state, "notes": ["request missing"], "plan": ""}

    resp = prompt_enhance_model.invoke([HumanMessage(content=f"{prompt_enhance_sys_pmt}\n\nUser request: {user_req}")])
    text = _text_from_model(resp)
    notes = state.get("notes") or []
    notes = notes + ["request enhanced"]
    return {**state, "plan": text, "notes": notes}


def plan_details(state: TravelState) -> TravelState:
    plan_seed = state.get("plan") or state.get("request") or ""
    duration = state.get("duration") or 3
    resp = detail_plan_model.invoke([HumanMessage(content=f"{detail_plan_sys_pmt}\n\nDuration: {duration} days\n\nContext:\n{plan_seed}")])
    text = _text_from_model(resp)
    notes = state.get("notes") or []
    notes = notes + [f"draft {duration}-day itinerary"]
    return {**state, "plan": text, "notes": notes}


def fetch_inventory(state: TravelState) -> TravelState:
    outputs = []
    origin = state.get("origin")
    dest = state.get("destination")
    depart = state.get("depart_date")

    if origin and dest and depart:
        outputs.append(
            find_flights.invoke({
                "origin": origin,
                "destination": dest,
                "depart_date": depart,
                "return_date": state.get("return_date"),
            })
        )
    else:
        outputs.append("Skipped flights: origin/destination/depart_date missing.")

    check_in = state.get("check_in")
    check_out = state.get("check_out")
    if dest and check_in and check_out:
        outputs.append(find_hotels.invoke({"destination": dest, "check_in": check_in, "check_out": check_out}))
    else:
        outputs.append("Skipped hotels: destination/check_in/check_out missing.")

    interests = state.get("interests")
    if dest:
        outputs.append(attraction_finder.invoke({"destination": dest, "interests": interests}))
        outputs.append(weather_checker.invoke({"destination": dest, "date": depart}))
    else:
        outputs.append("Skipped attractions/weather: destination missing.")

    notes = state.get("notes") or []
    notes = notes + ["tools attempted"]
    return {**state, "inventory": outputs, "notes": notes}


def route_after_plan(state: TravelState) -> str:
    """
    Conditional edge router after plan_details node.
    
    Routes to:
    - "human_review": if human approval is required
    - "tools": if tool calls are needed and no human approval needed
    - END: if neither human review nor tools needed
    """
    requires_human = state.get("requires_human_approval", False)
    needs_tools = state.get("tool_calls_needed", False)
    
    # Check if origin, destination, depart_date exist for tool calls
    has_core_fields = (
        state.get("origin") 
        and state.get("destination") 
        and state.get("depart_date")
    )
    
    if requires_human:
        return "human_review"
    elif has_core_fields or needs_tools:
        return "tools"
    else:
        return END


def human_review(state: TravelState) -> TravelState:
    """
    Human-in-the-loop node for plan approval/modifications.
    In a real scenario, this would pause for user input.
    """
    notes = state.get("notes") or []
    notes = notes + ["awaiting human approval"]
    return {**state, "notes": notes}



def build_graph():
    graph = StateGraph(TravelState)
    graph.add_node("enhance", enhance_request)
    graph.add_node("plan", plan_details)
    graph.add_node("tools", fetch_inventory)
    graph.add_node("human_review", human_review)

    graph.set_entry_point("enhance")
    graph.add_edge("enhance", "plan")
    
    # Conditional edge from plan based on human-in-loop and tool call needs
    graph.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "human_review": "human_review",
            "tools": "tools",
            END: END,
        }
    )
    
    # After human review, proceed to tools if needed
    graph.add_edge("human_review", "tools")
    graph.add_edge("tools", END)
    return graph.compile()


travel_graph = build_graph()
