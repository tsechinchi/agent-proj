"""Streamlit web interface for the travel planning agent.

This replaces the CLI deployment (main.py) with an interactive web UI.
Environment variables are loaded from .env before graph initialization.
"""

import logging
from dotenv import load_dotenv

# Load env before graph import so LLM/tool configs see variables.
load_dotenv()

import streamlit as st
from stategraph import travel_graph, TravelState
from agents.tools.tools import generate_pdf_itinerary, email_sender

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_session_state():
    """Initialize Streamlit session state for conversation history and form inputs."""
    if "history" not in st.session_state:
        st.session_state.history = []
    if "last_request" not in st.session_state:
        st.session_state.last_request = None


def run_travel_plan(request_text: str, origin: str, destination: str, depart_date: str,
                    return_date: str, check_in: str, check_out: str, interests: str,
                    duration: int) -> dict:
    """Execute the travel planning graph with the given inputs."""
    state: TravelState = {
        "request": request_text,
        "origin": origin or None,
        "destination": destination or None,
        "depart_date": depart_date or None,
        "return_date": return_date or None,
        "check_in": check_in or None,
        "check_out": check_out or None,
        "interests": interests or None,
        "duration": duration,
        "notes": [],
    }
    
    result = travel_graph.invoke(state)
    return result


def display_results(result: dict):
    """Display the results of the travel planning in formatted tabs."""
    st.divider()
    st.subheader("📋 Results")
    
    tab1, tab2, tab3 = st.tabs(["Plan", "Tool Results", "Execution Notes"])
    
    with tab1:
        plan_text = result.get("plan", "No plan generated.")
        st.markdown(plan_text)
    
    with tab2:
        inventory = result.get("inventory") or []
        if inventory:
            for idx, item in enumerate(inventory, 1):
                with st.expander(f"Result {idx}"):
                    st.write(item)
        else:
            st.info("No tool results available. Provide origin/destination/dates for tool calls.")
    
    with tab3:
        notes = result.get("notes") or []
        if notes:
            for note in notes:
                st.write(f"• {note}")
        else:
            st.write("No execution notes.")


def main():
    st.set_page_config(page_title="Travel Planner Agent", layout="wide")
    st.title("✈️ Travel Planning Agent")
    st.markdown("Create personalized travel itineraries with AI assistance.")
    
    initialize_session_state()
    
    # Form for travel request
    with st.form("travel_request_form"):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            request_text = st.text_area(
                "What kind of trip are you planning?",
                placeholder="E.g., 'I want a relaxing beach vacation with good food and hiking'",
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
        st.markdown("**Optional: Provide structured trip details for tool calls**")
        
        col1, col2 = st.columns(2)
        with col1:
            origin = st.text_input("Origin (e.g., JFK, NYC)", placeholder="Airport code or city")
            destination = st.text_input("Destination (e.g., LAX, Los Angeles)", placeholder="Airport code or city")
            interests = st.text_input("Interests (e.g., 'beaches, local food')", placeholder="Optional")
        
        with col2:
            depart_date = st.text_input("Departure Date", placeholder="YYYY-MM-DD")
            return_date = st.text_input("Return Date (optional)", placeholder="YYYY-MM-DD")
            check_in = st.text_input("Hotel Check-in (optional)", placeholder="YYYY-MM-DD")
            check_out = st.text_input("Hotel Check-out (optional)", placeholder="YYYY-MM-DD")

        # Post-generation options (captured with the form)
        generate_pdf = st.checkbox("Generate PDF of itinerary (requires ALLOW_AUTO_EMAIL_PDF=true)")
        send_email = st.checkbox("Send itinerary via email (requires SMTP and ALLOW_AUTO_EMAIL_PDF)")
        recipient_email = None
        if send_email:
            recipient_email = st.text_input("Recipient email for itinerary", placeholder="name@example.com")

        submit_btn = st.form_submit_button("Generate Travel Plan", use_container_width=True)
    
    if submit_btn:
        if not request_text.strip():
            st.error("Please enter a travel request.")
        else:
            with st.spinner("Planning your trip..."):
                try:
                    result = run_travel_plan(
                        request_text=request_text,
                        origin=origin,
                        destination=destination,
                        depart_date=depart_date,
                        return_date=return_date,
                        check_in=check_in,
                        check_out=check_out,
                        interests=interests,
                        duration=duration
                    )
                    
                    # Store in session history (ephemeral)
                    st.session_state.history.append({
                        "request": request_text,
                        "result": result
                    })

                    # Display results
                    display_results(result)

                    # Post-processing: PDF generation and optional email
                    pdf_resp = None
                    try:
                        if 'plan' in result and generate_pdf:
                            with st.spinner("Generating PDF..."):
                                pdf_resp = generate_pdf_itinerary.invoke({"itinerary_details": result.get('plan', '')})
                                st.write(f"PDF result: {pdf_resp}")
                        if send_email:
                            if not recipient_email:
                                st.warning("Email not sent: recipient email is empty.")
                            else:
                                with st.spinner("Sending email..."):
                                    attachment = None
                                    if isinstance(pdf_resp, str) and pdf_resp.endswith('.pdf'):
                                        attachment = pdf_resp
                                    email_resp = email_sender.invoke({
                                        "recipient_email": recipient_email,
                                        "subject": f"Your itinerary: {request_text[:40]}",
                                        "body": result.get('plan', ''),
                                        "attachment_path": attachment,
                                    })
                                    st.write(f"Email result: {email_resp}")
                    except Exception as e:
                        st.error(f"Post-processing error: {e}")

                    st.success("✅ Travel plan generated successfully!")
                    
                except Exception as e:
                    st.error(f"Error generating plan: {e}")
                    logger.exception("Error in travel plan generation")
    
    # Display previous results if any
    if st.session_state.history:
        with st.expander(f"📜 Previous Requests ({len(st.session_state.history)})"):
            for idx, entry in enumerate(st.session_state.history, 1):
                with st.expander(f"Request #{idx}: {entry['request'][:50]}..."):
                    display_results(entry['result'])


if __name__ == "__main__":
    main()
