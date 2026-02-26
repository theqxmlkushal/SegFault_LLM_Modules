"""
WanderAI LLM Modules - Core Pipeline Demo
Run this to test the M1-M3 flow interactively
"""
import os
import json
from dotenv import load_dotenv

# Load .env variables before anything else
load_dotenv()

from modules.m0_query_refiner import QueryRefiner
from modules.m1_intent_extractor import IntentExtractor
from modules.m2_destination_suggester import DestinationSuggester
from modules.m3_itinerary_builder import ItineraryBuilder

def print_header(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")

def print_itinerary(itinerary):
    print(f"📍 Destination: {itinerary.destination}")
    print(f"⏱️  Duration: {itinerary.duration} days")
    print(f"💰 Total Cost: {itinerary.total_estimated_cost}\n")
    
    for day in itinerary.days:
        print(f"DAY {day.day}: {day.title}")
        for slot in day.schedule:
            print(f"  {slot.time} - {slot.activity} (@ {slot.location})")
        print("-" * 40)

def main():
    print_header("WanderAI Core Pipeline - M1 to M3")
    
    # Initialize modules
    print("Initializing modules...")
    refiner = QueryRefiner()
    extractor = IntentExtractor()
    suggester = DestinationSuggester()
    builder = ItineraryBuilder()
    print("✓ Ready!\n")
    
    # Get user query
    user_query = ""
    while not user_query:
        print("Enter your travel query (e.g., 'Trip to Alibaug for 2 people, budget 5k'):")
        user_query = input("> ").strip()
    
    # Step 0: Refine Query
    print_header("Step 0: M0 - Query Refiner")
    refined_query = refiner.refine(user_query)
    print(f"Original: {user_query}")
    print(f"Refined:  {refined_query}")
    
    # Step 1: Extract Intent
    print_header("Step 1: M1 - Intent Extractor")
    intent = extractor.extract(refined_query)
    print(json.dumps(intent.model_dump(), indent=2))
    
    # Step 2: Suggest Destinations
    print_header("Step 2: M2 - Destination Suggester")
    suggestions = suggester.suggest(intent, top_k=3)
    print(f"Summary: {suggestions.summary}\n")
    for i, dest in enumerate(suggestions.destinations, 1):
        print(f"{i}. {dest.name} - Match: {dest.match_score}%")
    
    # Select best match
    chosen_dest = suggestions.destinations[0]
    print(f"\n✓ Selected: {chosen_dest.name}\n")
    
    # Step 3: Build Itinerary
    print_header("Step 3: M3 - Itinerary Builder")
    itinerary = builder.build(intent, chosen_dest)
    print_itinerary(itinerary)
    
    print_header("Demo Complete!")
    print("M1-M3 Pipeline executed successfully without M4.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
