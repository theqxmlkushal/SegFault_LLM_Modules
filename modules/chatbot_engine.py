"""
WanderAI Chatbot Engine
Core logic for the conversational travel assistant
"""
import logging
from typing import List, Dict, Any, Optional

from modules.m0_query_refiner import QueryRefiner
from modules.m1_intent_extractor import IntentExtractor
from modules.m2_destination_suggester import DestinationSuggester
from modules.m3_itinerary_builder import ItineraryBuilder
from modules.m6_place_description_generator import PlaceDescriptionGenerator

logger = logging.getLogger(__name__)

class WanderAIChatbotEngine:
    """
    State-less controller for the WanderAI chatbot.
    Designed for easy integration into backends (FastAPI, Flask, etc.)
    """
    def __init__(self):
        self.refiner = QueryRefiner()
        self.extractor = IntentExtractor()
        self.suggester = DestinationSuggester()
        self.builder = ItineraryBuilder()
        self.desc_gen = PlaceDescriptionGenerator()

    def process_message(self, 
                       user_input: str, 
                       history: List[Dict[str, str]], 
                       suggested_places: List[str] = None) -> Dict[str, Any]:
        """
        Main entry point for processing a chat message.
        
        Args:
            user_input: The message from the user
            history: List of previous messages in {"role": "User/Bot", "content": "..."} format
            suggested_places: List of place names already suggested to this user
            
        Returns:
            Dict containing:
            - response: Text for the user
            - state: Internal state updates (new_suggested_places, current_intent, etc.)
            - type: 'suggestion', 'itinerary', or 'clarification'
            - data: Raw data (itinerary object or destination object)
        """
        if suggested_places is None:
            suggested_places = []

        # 1. Format history for the refiner
        history_str = "\n".join([f"{h['role']}: {h['content']}" for h in history[-4:]])
        
        # 2. Refine Query with Context
        refined_query = self.refiner.refine(user_input, history_str)
        
        # 3. Extract Intent
        intent = self.extractor.extract(refined_query)
        
        # Handle Confirmation & Itinerary Building
        if intent.confirmation_place:
            # Re-suggest or find the destination object for the confirmed place
            # In a real backend, you might store the full destination object in the session
            # Here we search for it again to be safe
            suggestions = self.suggester.suggest(intent, top_k=1)
            if suggestions.destinations:
                chosen_dest = suggestions.destinations[0]
                itinerary = self.builder.build(intent, chosen_dest)
                return {
                    "response": f"Perfect! I've built a detailed itinerary for {chosen_dest.name}.",
                    "type": "itinerary",
                    "data": itinerary.model_dump(),
                    "refined_query": refined_query
                }

        # 4. Suggest Destinations
        suggestions = self.suggester.suggest(intent, top_k=5)
        
        # Find the best place not already suggested
        new_dest = None
        for dest in suggestions.destinations:
            if dest.name not in suggested_places:
                new_dest = dest
                break
        
        if not new_dest:
            new_dest = suggestions.destinations[0] # Fallback
            
        # 5. Get Description (M6)
        description = self.desc_gen.generate(new_dest.name)
        
        # 6. Construct Response
        response_text = f"Based on our chat, I suggest **{new_dest.name}**! \n\n{description}\n\n"
        
        # Check for missing factors humbly
        missing = []
        if not intent.budget: missing.append("budget")
        if not intent.duration_days: missing.append("duration")
        if not intent.interests: missing.append("interests")
        
        if missing:
            response_text += f"To help me tailor this even better, you could also mention your preference for: **{', '.join(missing)}**. "
        
        response_text += f"\n\nWould you like me to build a detailed plan for {new_dest.name}, or should we look for another option?"
        
        return {
            "response": response_text,
            "type": "suggestion",
            "data": new_dest.model_dump(),
            "suggested_place_name": new_dest.name,
            "refined_query": refined_query
        }
