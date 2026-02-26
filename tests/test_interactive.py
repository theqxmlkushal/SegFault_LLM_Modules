
import sys
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Add current directory to path
sys.path.append(os.getcwd())

# Silence background logs for a cleaner chat experience
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("modules").setLevel(logging.WARNING)
logging.basicConfig(level=logging.WARNING)

load_dotenv()

from modules.chatbot_engine import WanderAIChatbotEngineV2
from modules.chatbot_core import WanderAIChatbotCoreV3

def interactive_test():
    print("=== WanderAI Unified Bot Shell ===")
    print("Commands: 'engine v2', 'engine v3', 'summary', 'reset', 'exit'\n")
    
    # Initialize engines
    engines = {
        "v2": WanderAIChatbotEngineV2(),
        "v3": WanderAIChatbotCoreV3()
    }
    
    current_engine_key = "v2"
    session_id = None
    
    print(f"--- Currently using Engine: {current_engine_key.upper()} ---")

    while True:
        try:
            print(f"\n({current_engine_key.upper()})", end=" ")
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ['exit', 'quit']:
                print("Goodbye!")
                break
                
            if user_input.lower() == 'engine v2':
                current_engine_key = "v2"
                session_id = None
                print("--- Switched to Engine V2 (Session Reset) ---")
                continue

            if user_input.lower() == 'engine v3':
                current_engine_key = "v3"
                session_id = None
                print("--- Switched to Engine V3 (Session Reset) ---")
                continue
                
            if user_input.lower() == 'reset':
                session_id = None
                print("--- Session Reset ---")
                continue
                
            if user_input.lower() == 'summary' and session_id:
                engine = engines[current_engine_key]
                summary = engine.get_session_summary(session_id)
                print("\nSESSION SUMMARY:")
                print(json.dumps(summary, indent=2, default=str))
                continue

            # Process message with active engine
            engine = engines[current_engine_key]
            result = engine.process_message(user_input, session_id=session_id)
            
            # Update session_id if it was None
            if not session_id:
                session_id = result['session_id']
            
            print(f"\nBot:")
            print("-" * 30)
            print(result.get('response', 'No response received.'))
            print("-" * 30)
            
            if result.get('type') == 'itinerary' and result.get('data'):
                dest = result['data'].get('destination') or result['data'].get('name', 'selected destination')
                print(f"(Itinerary generated for {dest})")
                # Print the full structured itinerary so the user can inspect it
                try:
                    print('\nFull itinerary data:')
                    print(json.dumps(result.get('data'), indent=2, default=str))
                except Exception:
                    # Fallback: pretty-print key-values
                    print('\nItinerary (raw):')
                    for k, v in (result.get('data') or {}).items():
                        print(f"- {k}: {v}")
                
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            # traceback.print_exc()

if __name__ == "__main__":
    interactive_test()
