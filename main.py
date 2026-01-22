#!/usr/bin/env python3
"""CLI entry point for the travel planner with interactive human-in-the-loop review.

This module provides a command-line interface for running the travel planning
graph with proper pause-and-resume functionality for human approval/feedback.

Usage:
    python main.py                          # Interactive mode
    python main.py --request "Paris trip"   # Quick mode with inline request
    python main.py --auto                   # Auto-approve (no human review)
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv

# Load environment variables first
load_dotenv()
load_dotenv("keys.env", override=True)

from stategraph import (
    TravelState,
    run_until_human_review,
    continue_after_feedback,
    get_current_plan,
    format_tool_results_for_display,
    MAX_ITERATIONS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def get_user_input(prompt: str, default: Optional[str] = None) -> str:
    """Get user input with optional default value."""
    if default:
        full_prompt = f"{prompt} [{default}]: "
    else:
        full_prompt = f"{prompt}: "
    
    try:
        value = input(full_prompt).strip()
        return value if value else (default or "")
    except EOFError:
        return default or ""


def validate_date(date_str: str) -> bool:
    """Validate date format YYYY-MM-DD."""
    if not date_str:
        return True  # Empty is valid (optional)
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def collect_trip_details() -> TravelState:
    """Interactive wizard to collect trip details from user."""
    print("\n" + "=" * 60)
    print("✈️  TRAVEL PLANNER - Trip Details Wizard")
    print("=" * 60)
    print("(Press Enter to skip optional fields)\n")
    
    # Required: Natural language request
    request = get_user_input("Describe your ideal trip")
    while not request:
        print("⚠️  Please provide a trip description.")
        request = get_user_input("Describe your ideal trip")
    
    # Duration
    duration_str = get_user_input("Trip duration (days)", "3")
    try:
        duration = int(duration_str) if duration_str else 3
    except ValueError:
        duration = 3
    
    print("\n--- Optional: Structured Details (for tool searches) ---\n")
    
    # Origin & Destination
    origin = get_user_input("Origin (airport code or city, e.g., JFK, NYC)")
    destination = get_user_input("Destination (airport code or city, e.g., NYC, New York)")
    
    # Dates
    default_depart = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    depart_date = get_user_input(f"Departure date (YYYY-MM-DD)", default_depart)
    while depart_date and not validate_date(depart_date):
        print("⚠️  Invalid date format. Use YYYY-MM-DD.")
        depart_date = get_user_input(f"Departure date (YYYY-MM-DD)", default_depart)
    
    default_return = ""
    if depart_date and duration > 1:
        try:
            dep = datetime.strptime(depart_date, "%Y-%m-%d")
            default_return = (dep + timedelta(days=duration)).strftime("%Y-%m-%d")
        except ValueError:
            pass
    
    return_date = get_user_input(f"Return date (YYYY-MM-DD)", default_return)
    while return_date and not validate_date(return_date):
        print("⚠️  Invalid date format. Use YYYY-MM-DD.")
        return_date = get_user_input(f"Return date (YYYY-MM-DD)", default_return)
    
    # Hotel dates
    check_in = get_user_input("Hotel check-in (YYYY-MM-DD)", depart_date)
    while check_in and not validate_date(check_in):
        print("⚠️  Invalid date format. Use YYYY-MM-DD.")
        check_in = get_user_input("Hotel check-in (YYYY-MM-DD)", depart_date)
    
    check_out = get_user_input("Hotel check-out (YYYY-MM-DD)", return_date)
    while check_out and not validate_date(check_out):
        print("⚠️  Invalid date format. Use YYYY-MM-DD.")
        check_out = get_user_input("Hotel check-out (YYYY-MM-DD)", return_date)
    
    # Interests
    interests = get_user_input("Interests (e.g., 'museums, hiking, food')")
    
    # Build initial state
    state: TravelState = {
        "request": request,
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
        "execution_mode": "cli",
    }
    
    return state


def display_plan(state: TravelState) -> None:
    """Display the current plan in a formatted way."""
    print("\n" + "=" * 60)
    print("📋 ITINERARY")
    print("=" * 60)
    print(get_current_plan(state))
    
    # Show tool results summary
    tool_results = state.get("tool_results", {})
    if tool_results:
        print("\n" + "-" * 40)
        print("📊 AVAILABLE TOOL DATA")
        print("-" * 40)
        print(format_tool_results_for_display(tool_results))


def display_execution_notes(state: TravelState) -> None:
    """Display execution notes for debugging/transparency."""
    notes = state.get("notes", [])
    if notes:
        print("\n" + "-" * 40)
        print("🔧 EXECUTION LOG")
        print("-" * 40)
        for note in notes:
            print(f"  • {note}")


def human_review_cli(state: TravelState) -> TravelState:
    """Interactive human review loop in CLI.
    
    Pauses for user input and updates state based on choice:
    - Approve: Returns with approved=True
    - Modify: Returns with human_feedback set
    - Regenerate: Returns with human_feedback="regenerate from scratch"
    """
    iteration = state.get("iteration_count", 0)
    
    print("\n" + "=" * 60)
    print(f"👤 HUMAN REVIEW (Iteration {iteration + 1}/{MAX_ITERATIONS})")
    print("=" * 60)
    
    display_plan(state)
    
    print("\n" + "-" * 40)
    print("OPTIONS:")
    print("  [a] Approve - Finalize this itinerary")
    print("  [m] Modify  - Request specific changes")
    print("  [r] Regenerate - Start over with same inputs")
    print("  [d] Debug   - Show execution details")
    print("  [q] Quit    - Exit without saving")
    print("-" * 40)
    
    while True:
        choice = get_user_input("Your choice", "a").lower()
        
        if choice in ("a", "approve"):
            print("\n✅ Plan approved!")
            return {
                **state,
                "approved": True,
                "awaiting_review": False,
                "iteration_count": iteration + 1,
            }
        
        elif choice in ("m", "modify"):
            feedback = get_user_input("What changes would you like?")
            if not feedback:
                print("⚠️  Please describe the changes you want.")
                continue
            print(f"\n📝 Feedback recorded: {feedback}")
            return {
                **state,
                "approved": False,
                "awaiting_review": False,
                "human_feedback": feedback,
                "iteration_count": iteration + 1,
            }
        
        elif choice in ("r", "regenerate"):
            print("\n🔄 Regenerating plan from scratch...")
            return {
                **state,
                "approved": False,
                "awaiting_review": False,
                "human_feedback": "regenerate from scratch",
                "iteration_count": iteration + 1,
            }
        
        elif choice in ("d", "debug"):
            display_execution_notes(state)
            continue
        
        elif choice in ("q", "quit"):
            print("\n👋 Exiting without finalizing.")
            sys.exit(0)
        
        else:
            print(f"⚠️  Unknown option: '{choice}'. Please choose a, m, r, d, or q.")


def run_travel_planner(initial_state: TravelState, auto_approve: bool = False) -> TravelState:
    """Run the travel planning workflow with human-in-the-loop.
    
    Args:
        initial_state: Initial TravelState with user input
        auto_approve: If True, skip human review and auto-approve
        
    Returns:
        Final TravelState with approved plan
    """
    print("\n" + "=" * 60)
    print("🚀 STARTING TRAVEL PLANNER")
    print("=" * 60)
    
    # Phase 1: Run graph until human review
    print("\n⏳ Generating initial plan...")
    state = run_until_human_review(initial_state)
    
    # Human review loop
    while True:
        # Check if we've hit max iterations
        iteration = state.get("iteration_count", 0)
        if iteration >= MAX_ITERATIONS:
            print(f"\n⚠️ Maximum iterations ({MAX_ITERATIONS}) reached. Finalizing...")
            state = {**state, "approved": True, "awaiting_review": False}
            break
        
        # Check if graph is waiting for human input
        if state.get("awaiting_review"):
            if auto_approve:
                print("\n🤖 Auto-approving plan (--auto flag)")
                state = {
                    **state,
                    "approved": True,
                    "awaiting_review": False,
                    "iteration_count": iteration + 1,
                }
            else:
                # Interactive human review
                state = human_review_cli(state)
        
        # If approved, we're done
        if state.get("approved"):
            break
        
        # If feedback provided, continue refinement
        if state.get("human_feedback"):
            print(f"\n⏳ Refining plan based on feedback...")
            state = continue_after_feedback(state)
        else:
            # No feedback and not approved - something went wrong
            logger.warning("Unexpected state: not approved, no feedback, not awaiting review")
            break
    
    # Final output
    print("\n" + "=" * 60)
    print("✅ FINAL ITINERARY")
    print("=" * 60)
    print(get_current_plan(state))
    
    display_execution_notes(state)
    
    return state


def quick_run(request: str, destination: Optional[str] = None, duration: int = 3) -> TravelState:
    """Quick run with minimal inputs (for scripting/testing)."""
    from datetime import datetime, timedelta
    
    depart = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    return_d = (datetime.now() + timedelta(days=30 + duration)).strftime("%Y-%m-%d")
    
    state: TravelState = {
        "request": request,
        "destination": destination,
        "depart_date": depart,
        "return_date": return_d,
        "check_in": depart,
        "check_out": return_d,
        "duration": duration,
        "messages": [],
        "notes": [],
        "approved": False,
        "awaiting_review": False,
        "iteration_count": 0,
        "tool_results": {},
        "selected_tools": [],
        "execution_mode": "cli",
    }
    
    return state


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Travel Planner CLI - Create personalized travel itineraries"
    )
    parser.add_argument(
        "--request", "-r",
        type=str,
        help="Quick mode: provide travel request directly"
    )
    parser.add_argument(
        "--destination", "-d",
        type=str,
        help="Quick mode: destination city or airport code"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=3,
        help="Trip duration in days (default: 3)"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-approve generated plan (no human review)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine run mode
    if args.request:
        # Quick mode with command-line args
        state = quick_run(
            request=args.request,
            destination=args.destination,
            duration=args.duration
        )
    else:
        # Interactive wizard mode
        state = collect_trip_details()
    
    # Run the planner
    try:
        final_state = run_travel_planner(state, auto_approve=args.auto)
        
        # Show success message
        print("\n" + "=" * 60)
        print("🎉 Trip planning complete!")
        print("=" * 60)
        
        # Offer to run Streamlit for richer experience
        print("\nTip: For a richer experience, run the Streamlit UI:")
        print("  streamlit run web_api.py")
        
    except KeyboardInterrupt:
        print("\n\n👋 Planning cancelled by user.")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Error during planning: {e}")
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
