"""Tiny CLI runner for the travel graph.

Usage:
	python main.py "Trip request text" --origin JFK --destination LAX --depart 2025-06-01 --return 2025-06-10 --check-in 2025-06-01 --check-out 2025-06-05 --interests "food markets" --duration 7

With no flags, it defaults to a 3-day plan; tools are skipped unless
origin/destination/depart are provided. Uses mock LLMs when OPENAI_API_KEY is
unset.
"""

import argparse
import logging

from dotenv import load_dotenv

# Load env before graph import so LLM/tool configs see variables.
load_dotenv()

from stategraph import travel_graph, TravelState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser(description="Run the travel planner graph")
    p.add_argument("request", help="User travel request text")
    p.add_argument("--origin")
    p.add_argument("--destination")
    p.add_argument("--depart")
    p.add_argument("--return-date")
    p.add_argument("--check-in")
    p.add_argument("--check-out")
    p.add_argument("--interests")
    p.add_argument("--duration", type=int, default=3, help="Trip duration in days (default: 3)")
    return p.parse_args()


def main():
    args = parse_args()
    state: TravelState = {
        "request": args.request,
        "origin": args.origin,
        "destination": args.destination,
        "depart_date": args.depart,
        "return_date": args.return_date,
        "check_in": args.check_in,
        "check_out": args.check_out,
        "interests": args.interests,
        "duration": args.duration,
        "notes": [],
    }

    app = travel_graph
    result = app.invoke(state)

    print("\n--- Plan ---")
    print(result.get("plan", ""))

    inventory = result.get("inventory") or []
    if inventory:
        print("\n--- Tool Results ---")
        for item in inventory:
            print("-", item)

    notes = result.get("notes") or []
    if notes:
        print("\n--- Notes ---")
        for n in notes:
            print("*", n)


if __name__ == "__main__":
    main()
