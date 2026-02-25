"""
WanderAI Backend Integration Example (FastAPI-style)
Shows how to use WanderAIChatbotEngine in a real web server
"""
import os
from typing import List, Dict, Optional
from pydantic import BaseModel
from dotenv import load_dotenv

# Note: You would normally use 'pip install fastapi uvicorn'
# This is a mock example to show the pattern

load_dotenv()
from modules.chatbot_engine import WanderAIChatbotEngine

# Initialize the engine once
engine = WanderAIChatbotEngine()

class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, str]]
    suggested_places: Optional[List[str]] = []

def chat_endpoint(request: ChatRequest):
    """
    Example endpoint: POST /api/chat
    """
    # 1. State is passed from the frontend/session
    user_input = request.message
    history = request.history
    suggested = request.suggested_places
    
    # 2. Process with the engine
    # The engine is stateless; you provide the context (history/suggested)
    result = engine.process_message(user_input, history, suggested)
    
    # 3. Return response to frontend
    return {
        "reply": result['response'],
        "type": result['type'],
        "data": result['data'], # Itinerary or Destination object
        "suggested_place_name": result.get('suggested_place_name') # Frontend should add this to session
    }

if __name__ == "__main__":
    print("--- Backend Integration Example ---")
    print("This file demonstrates the API pattern for backend integration.")
    print("See modules/chatbot_engine.py for the core logic.")
    
    # Simple test
    mock_request = ChatRequest(
        message="I want to go to a beach",
        history=[],
        suggested_places=[]
    )
    res = chat_endpoint(mock_request)
    print(f"\nAPI Response:\n{res['reply'][:100]}...")
