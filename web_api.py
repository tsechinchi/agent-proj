"""Streamlit web interface for the travel planner with session-based human review.

This integrates the refactored travel planning graph with Streamlit UI,
pausing at the human_review node to capture user feedback/approval.

Key Features:
- Session-based state persistence across reruns
- Interactive plan review with approve/modify/regenerate options
- Iteration loop support with max iteration safeguard
- Tool data display and integration
"""

import logging
import json
from dotenv import load_dotenv

# Load env before graph import
load_dotenv()
load_dotenv("keys.env", override=True)

import streamlit as st
from stategraph import (
    travel_graph,
    TravelState,
    run_until_human_review,
    continue_after_feedback,
    get_current_plan,
    format_tool_results_for_display,
    MAX_ITERATIONS,
)
from langchain_core.messages import BaseMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_session_state():
    """Initialize Streamlit session state for multi-step workflow."""
    if "current_state" not in st.session_state:
        st.session_state.current_state = None
    if "awaiting_review" not in st.session_state:
        st.session_state.awaiting_review = False
    if "history" not in st.session_state:
        st.session_state.history = []
    if "processing" not in st.session_state:
        st.session_state.processing = False


def serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    """Convert LangChain messages to serializable format for session state."""
    if not messages:
        return []
    return [
        {
            "type": msg.__class__.__name__,
            "content": msg.content if hasattr(msg, "content") else str(msg)
        }
        for msg in messages
    ]


def run_graph_to_review(state: TravelState) -> TravelState:
    """Run graph up to human_review node, then pause."""
    try:
        result = run_until_human_review(state)
        return result
    except Exception as e:
        logger.exception(f"Error running graph: {e}")
        raise


def process_user_feedback(action: str, feedback: str = "") -> None:
    """Process user feedback and continue graph execution.
    
    Args:
        action: One of 'approve', 'modify', 'regenerate'
        feedback: User's modification feedback (for 'modify' action)
    """
    if not st.session_state.current_state:
        return
    
    state = st.session_state.current_state
    iteration = state.get("iteration_count", 0)
    
    if action == "approve":
        # User approved - finalize
        state["approved"] = True
        state["awaiting_review"] = False
        state["iteration_count"] = iteration + 1
        logger.info("User approved plan")
        
    elif action == "modify":
        # User wants modifications - set feedback and continue
        state["approved"] = False
        state["awaiting_review"] = False
        state["human_feedback"] = feedback
        state["iteration_count"] = iteration + 1
        logger.info(f"User requested modifications: {feedback}")
        
        # Continue refinement
        st.session_state.processing = True
        try:
            state = continue_after_feedback(state)
        except Exception as e:
            logger.exception(f"Error continuing after feedback: {e}")
            st.error(f"Error processing feedback: {e}")
        finally:
            st.session_state.processing = False
        
    elif action == "regenerate":
        # User wants fresh start
        state["approved"] = False
        state["awaiting_review"] = False
        state["human_feedback"] = "regenerate from scratch"
        state["iteration_count"] = iteration + 1
        logger.info("User requested regeneration")
        
        # Continue refinement
        st.session_state.processing = True
        try:
            state = continue_after_feedback(state)
        except Exception as e:
            logger.exception(f"Error regenerating: {e}")
            st.error(f"Error regenerating plan: {e}")
        finally:
            st.session_state.processing = False
    
    # Update session state
    st.session_state.current_state = state
    
    # Check if we need to continue reviewing or if we're done
    if state.get("approved"):
        st.session_state.awaiting_review = False
    elif state.get("awaiting_review"):
        st.session_state.awaiting_review = True
    else:
        st.session_state.awaiting_review = False


def display_plan_review(state: TravelState):
    """Display plan and review form for user approval."""
    plan = state.get("plan", state.get("draft_plan", ""))
    tool_results = state.get("tool_results", {})
    iteration = state.get("iteration_count", 0)
    
    st.subheader("📋 Plan Review")
    
    # Show iteration progress
    progress = min(iteration / MAX_ITERATIONS, 1.0)
    st.progress(progress, text=f"Iteration {iteration + 1} of {MAX_ITERATIONS}")
    
    if iteration >= MAX_ITERATIONS - 1:
        st.warning(f"⚠️ This is your last iteration. The plan will be finalized after this review.")
    
    # Display the plan
    st.markdown(plan)
    
    # Show available tool data
    if tool_results:
        st.markdown("---")
        with st.expander("📊 Tool Data Available", expanded=False):
            for tool_name, data in tool_results.items():
                if data and not str(data).startswith("Error"):
                    with st.expander(f"📍 {tool_name.title()}"):
                        st.write(str(data)[:1000] + ("..." if len(str(data)) > 1000 else ""))
    
    st.markdown("---")
    
    # Review actions - using columns for buttons
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("✅ Approve Plan", key="btn_approve", use_container_width=True, type="primary"):
            process_user_feedback("approve")
            st.rerun()
    
    with col2:
        if st.button("🔄 Regenerate", key="btn_regenerate", use_container_width=True):
            process_user_feedback("regenerate")
            st.rerun()
    
    with col3:
        # Debug toggle
        if st.button("🔧 Show Debug", key="btn_debug", use_container_width=True):
            st.session_state.show_debug = not st.session_state.get("show_debug", False)
            st.rerun()
    
    # Modification feedback form
    st.markdown("### 📝 Request Modifications")
    feedback = st.text_area(
        "What changes would you like?",
        placeholder="E.g., 'Move the museum visit to Day 2' or 'Find cheaper hotels' or 'Add more outdoor activities'",
        key="modification_feedback"
    )
    
    if st.button("📝 Submit Feedback & Refine", key="btn_modify", use_container_width=True):
        if feedback.strip():
            process_user_feedback("modify", feedback.strip())
            st.rerun()
        else:
            st.warning("Please describe what you'd like to change.")
    
    # Debug information
    if st.session_state.get("show_debug", False):
        st.markdown("---")
        with st.expander("🔧 Debug Information", expanded=True):
            notes = state.get("notes", [])
            if notes:
                st.write("**Execution Log:**")
                for note in notes:
                    st.write(f"• {note}")
            st.write("**State Summary:**")
            st.json({
                "iteration_count": state.get("iteration_count"),
                "approved": state.get("approved"),
                "awaiting_review": state.get("awaiting_review"),
                "selected_tools": state.get("selected_tools"),
                "has_feedback": bool(state.get("human_feedback")),
            })


def display_results(result: dict):
    """Display travel planning results in tabs."""
    st.divider()
    st.subheader("📋 Final Itinerary")
    
    tab1, tab2, tab3 = st.tabs(["Itinerary", "Tool Data", "Execution Log"])
    
    with tab1:
        plan_text = result.get("plan", result.get("draft_plan", "No plan generated."))
        st.markdown(plan_text)
        
        # Download button for the plan
        st.download_button(
            label="📥 Download Itinerary",
            data=plan_text,
            file_name="travel_itinerary.md",
            mime="text/markdown",
        )
    
    with tab2:
        tool_results = result.get("tool_results", {})
        if tool_results:
            for tool_name, data in tool_results.items():
                if data and not str(data).startswith("Error"):
                    with st.expander(f"📍 {tool_name.title()}", expanded=False):
                        st.write(str(data))
        else:
            st.info("No tool data was collected for this plan.")
    
    with tab3:
        notes = result.get("notes", [])
        if notes:
            for note in notes:
                st.write(f"• {note}")
        else:
            st.write("No execution notes.")
        
        # Summary stats
        st.markdown("---")
        st.write("**Summary:**")
        st.write(f"- Total iterations: {result.get('iteration_count', 0)}")
        st.write(f"- Tools used: {', '.join(result.get('selected_tools', [])) or 'None'}")


def main():
    st.set_page_config(page_title="Travel Planner Agent", layout="wide")
    st.title("✈️ Travel Planning Agent")
    st.markdown("Create personalized travel itineraries with AI assistance and interactive review.")
    
    initialize_session_state()
    
    # Show processing indicator
    if st.session_state.get("processing", False):
        st.info("⏳ Processing your request...")
        return
    
    # Check if we're in review mode
    if st.session_state.awaiting_review and st.session_state.current_state:
        st.warning("⏸️ Plan ready for review - Please approve or request modifications")
        display_plan_review(st.session_state.current_state)
        return  # Don't show form, stay in review mode
    
    # Check if we have an approved plan to display
    if st.session_state.current_state and st.session_state.current_state.get("approved"):
        st.success("✅ Itinerary approved and finalized!")
        display_results(st.session_state.current_state)
        
        # Option to start new plan
        if st.button("🆕 Start New Trip Plan", use_container_width=True):
            # Add to history before clearing
            st.session_state.history.append({
                "request": st.session_state.current_state.get("request", "Unknown"),
                "result": st.session_state.current_state
            })
            st.session_state.current_state = None
            st.session_state.awaiting_review = False
            st.rerun()
        return
    
    # Form for new travel request
    with st.form("travel_request_form"):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            request_text = st.text_area(
                "What kind of trip are you planning?",
                placeholder="E.g., 'I want a relaxing beach vacation with good food and hiking opportunities'",
                height=100
            )
        
        with col2:
            duration = st.number_input(
                "Trip Duration (days)",
                min_value=1,
                max_value=365,
                value=3,
                step=1
            )
        
        st.markdown("---")
        st.markdown("**Optional: Provide structured trip details for accurate tool searches**")
        
        col1, col2 = st.columns(2)
        with col1:
            origin = st.text_input("Origin (e.g., JFK, NYC)", placeholder="Airport code or city")
            destination = st.text_input("Destination (e.g., NYC, New York)", placeholder="Airport code or city")
            interests = st.text_input("Interests (e.g., 'museums, hiking, food')", placeholder="Optional")
        
        with col2:
            depart_date = st.text_input("Departure Date", placeholder="YYYY-MM-DD")
            return_date = st.text_input("Return Date (optional)", placeholder="YYYY-MM-DD")
            check_in = st.text_input("Hotel Check-in (optional)", placeholder="YYYY-MM-DD")
            check_out = st.text_input("Hotel Check-out (optional)", placeholder="YYYY-MM-DD")
        
        submit_btn = st.form_submit_button("🚀 Generate Travel Plan", use_container_width=True, type="primary")
    
    if submit_btn:
        if not request_text.strip():
            st.error("Please enter a travel request.")
        else:
            # Initialize planning state
            state: TravelState = {
                "request": request_text,
                "origin": origin if origin else None,
                "destination": destination if destination else None,
                "depart_date": depart_date if depart_date else None,
                "return_date": return_date if return_date else None,
                "check_in": check_in if check_in else None,
                "check_out": check_out if check_out else None,
                "interests": interests if interests else None,
                "duration": duration,
                "messages": [],
                "notes": [],
                "approved": False,
                "awaiting_review": False,
                "iteration_count": 0,
                "tool_results": {},
                "selected_tools": [],
                "execution_mode": "streamlit",
            }
            
            with st.spinner("🚀 Planning your trip... This may take a moment."):
                try:
                    result = run_graph_to_review(state)
                    
                    # Store in session state for review
                    st.session_state.current_state = result
                    st.session_state.awaiting_review = result.get("awaiting_review", True)
                    
                    logger.info("Plan generated, awaiting user review")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error generating plan: {e}")
                    logger.exception("Error in travel plan generation")
    
    # Show history in sidebar
    if st.session_state.history:
        with st.sidebar:
            st.subheader(f"📜 History ({len(st.session_state.history)} trips)")
            for idx, entry in enumerate(reversed(st.session_state.history), 1):
                with st.expander(f"Trip #{len(st.session_state.history) - idx + 1}: {entry['request'][:30]}..."):
                    st.write(f"**Request:** {entry['request']}")
                    plan = entry['result'].get('plan', entry['result'].get('draft_plan', 'N/A'))
                    st.write(f"**Plan preview:** {plan[:200]}...")


if __name__ == "__main__":
    main()
