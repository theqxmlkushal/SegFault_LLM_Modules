"""
WanderAI Conversational Chatbot (Terminal Interface)
Demonstrates the use of WanderAIChatbotEngine
"""
import os
import logging
from dotenv import load_dotenv
from modules.chatbot_engine import WanderAIChatbotEngine

# Load .env
load_dotenv()

# Configure logging to be quiet for terminal demo
logging.basicConfig(level=logging.ERROR)

def main():
    engine = WanderAIChatbotEngine()
    history = []
    suggested_places = []
    
    print("\n" + "="*50)
    print("   WanderAI Conversational Assistant")
    print("="*50 + "\n")
    print("✨ WanderAI: Hey! 👋 Tell me what you're thinking for your next trip. I can suggest places and build plans!")

    while True:
        user_input = input("\n> ").strip()
        if user_input.lower() in ['exit', 'quit', 'bye']:
            print("\n✨ WanderAI: Happy travels! Goodbye! ✈️")
            break
        
        if not user_input:
            continue

        # Process message using the engine
        result = engine.process_message(user_input, history, suggested_places)
        
        # Display response
        print(f"\n✨ WanderAI: {result['response']}")
        
        # Handle itinerary display
        if result['type'] == 'itinerary':
            data = result['data']
            print("\n" + "-"*40)
            print(f"📍 Destination: {data['destination']}")
            print(f"⏱️  Duration: {data['duration']} days")
            print(f"💰 Total Cost: {data['total_estimated_cost']}")
            print("-"*40)
            for day in data['days']:
                print(f"\nDAY {day['day']}: {day['title']}")
                for slot in day['schedule']:
                    print(f"  {slot['time']} - {slot['activity']} (@ {slot['location']})")
            print("-"*40)
            # Reset history/suggestions after building itinerary if desired, 
            # but usually we just keep going.
        
        # Update State
        history.append({"role": "User", "content": user_input})
        history.append({"role": "Bot", "content": result['response']})
        
        if 'suggested_place_name' in result:
            suggested_places.append(result['suggested_place_name'])

if __name__ == "__main__":
    main()
