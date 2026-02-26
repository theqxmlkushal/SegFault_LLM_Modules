"""
WanderAI Chatbot Engine V2
Enhanced with intent-based routing, session state, and hallucination prevention
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
from pydantic import BaseModel, Field

from modules.m0_query_refiner import QueryRefiner
from modules.m1_intent_extractor import IntentExtractor
from modules.m2_destination_suggester import DestinationSuggester
from modules.m3_itinerary_builder import ItineraryBuilder
from modules.m6_place_description_generator import PlaceDescriptionGenerator
from modules.routing_engine import RoutingEngine, IntentType
from modules.response_generator import ResponseVariationGenerator

from utils.llm_client import LLMClient
from utils.rag_engine import SimpleRAG
from utils.webhook_manager import WebhookManager

logger = logging.getLogger(__name__)


class ChatSession(BaseModel):
    """Session-aware conversation context"""
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    last_message_at: datetime = Field(default_factory=datetime.now)
    message_history: List[Dict[str, str]] = Field(default_factory=list)
    topics_discussed: set = Field(default_factory=set)
    previous_responses: Dict[str, str] = Field(default_factory=dict)
    suggested_places: List[str] = Field(default_factory=list)
    knowledge_base_timestamp: datetime = Field(default_factory=datetime.now)
    user_preferences: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True

    def update_timestamp(self):
        self.last_message_at = datetime.now()

    def add_message(self, role: str, content: str):
        self.message_history.append({"role": role, "content": content})
        # Keep only last 20 messages for performance
        if len(self.message_history) > 20:
            self.message_history = self.message_history[-20:]
        self.update_timestamp()

    def add_topic(self, topic: str):
        self.topics_discussed.add(topic.lower())


class WanderAIChatbotEngineV2:
    """
    Enhanced chatbot engine with:
    - Intent-based routing (decides when to use modules vs RAG-only)
    - Session state management
    - Hallucination prevention via RAG grounding
    - Response variation to avoid repetition
    - Knowledge base freshness tracking
    - Webhook support for KB updates
    """

    def __init__(self,
                 rag_engine: Optional[SimpleRAG] = None,
                 webhook_manager: Optional[WebhookManager] = None,
                 llm_client: Optional[LLMClient] = None):
        # Core modules
        self.refiner = QueryRefiner()
        self.extractor = IntentExtractor()
        self.suggester = DestinationSuggester()
        self.builder = ItineraryBuilder()
        self.desc_gen = PlaceDescriptionGenerator()

        # New feature modules
        self.router = RoutingEngine(llm_client)
        self.variation_gen = ResponseVariationGenerator(llm_client)

        # Infrastructure
        self.rag = rag_engine or SimpleRAG()
        self.webhook_manager = webhook_manager
        self.llm_client = llm_client or LLMClient()

        # Session management
        self.sessions: Dict[str, ChatSession] = {}

    def get_or_create_session(self, session_id: Optional[str] = None) -> ChatSession:
        """Get existing session or create new one"""
        if session_id and session_id in self.sessions:
            return self.sessions[session_id]

        session = ChatSession()
        self.sessions[session.session_id] = session
        return session

    def process_message(self,
                       user_input: str,
                       session_id: Optional[str] = None,
                       refresh_kb: bool = False) -> Dict[str, Any]:
        """
        Main entry point for processing a chat message.

        Args:
            user_input: The message from the user
            session_id: Optional session ID to continue conversation
            refresh_kb: Whether to refresh knowledge base from webhook updates

        Returns:
            Dict containing:
            - response: Text for the user
            - type: 'suggestion', 'itinerary', 'general_chat', or 'clarification'
            - data: Raw structured data (if applicable)
            - sources: KB sources used (for transparency)
            - kb_timestamp: When KB was last updated
            - session_id: Session ID for next request
        """
        # Session management
        session = self.get_or_create_session(session_id)
        session.add_message("User", user_input)

        # Refresh KB if needed
        if refresh_kb and self.webhook_manager:
            self.rag.load_knowledge_base()  # Reload from disk

        session.knowledge_base_timestamp = self.rag.knowledge_base_timestamp

        # Step 1: Intent routing
        intent_decision = self.router.classify(
            user_input,
            session.message_history
        )

        logger.info(f"[{session.session_id}] Intent: {intent_decision.intent_type.value} "
                   f"(confidence: {intent_decision.confidence:.2f})")

        # Step 2: Handle out-of-scope
        if intent_decision.intent_type == IntentType.OUT_OF_SCOPE:
            response = self._handle_out_of_scope(user_input, session)
            session.add_message("Bot", response)
            return {
                "response": response,
                "type": "clarification",
                "session_id": session.session_id,
                "kb_timestamp": session.knowledge_base_timestamp.isoformat()
            }

        # Step 3: Handle based on intent
        if intent_decision.requires_modules:
            # Use M1/M2/M3 pipeline for structured task queries
            return self._handle_module_pipeline(user_input, session, intent_decision)
        else:
            # Use RAG-only general chat mode
            return self._handle_general_chat(user_input, session, intent_decision)

    def _handle_module_pipeline(self,
                               user_input: str,
                               session: ChatSession,
                               intent_decision) -> Dict[str, Any]:
        """Handle trip suggestion / itinerary request using module pipeline"""

        # Refine query with conversation context
        history_str = "\n".join([f"{h['role']}: {h['content']}" for h in session.message_history[-4:-1]])
        refined_query = self.refiner.refine(user_input, history_str)

        # Extract intent
        intent = self.extractor.extract(refined_query)
        
        # Only update preferences if we have a valid destination or specific values
        # This prevents "None" from overwriting valid context unless it's a new trip
        if intent.budget: session.user_preferences["budget"] = intent.budget
        if intent.duration_days: session.user_preferences["duration"] = intent.duration_days
        if intent.group_size: session.user_preferences["group_size"] = intent.group_size
        if intent.interests: session.user_preferences["interests"] = intent.interests

        # Handle itinerary building
        if intent.confirmation_place or intent_decision.intent_type == IntentType.ITINERARY_REQUEST:
            suggestions = self.suggester.suggest(intent, top_k=1)
            if suggestions.destinations:
                chosen_dest = suggestions.destinations[0]
                
                # If budget is impossible, be honest and don't pretend it's "Perfect"
                if chosen_dest.match_score < 40 or "Warning" in chosen_dest.reasoning:
                    response_text = f"I've looked into your request for {chosen_dest.name}, but I have some concerns: \n\n"
                    response_text += f"{chosen_dest.reasoning}\n\n"
                    response_text += f"Because of this, a 3-day full itinerary might not be practical. "
                    response_text += "Would you like to try a shorter trip, or should we adjust the budget?"
                    
                    session.add_message("Bot", response_text)
                    return {
                        "response": response_text,
                        "type": "clarification",
                        "session_id": session.session_id,
                        "kb_timestamp": session.knowledge_base_timestamp.isoformat(),
                        "refined_query": refined_query
                    }

                # Feasible trip flow
                itinerary = self.builder.build(intent, chosen_dest)

                # Retry once if the builder returned an empty itinerary
                if not getattr(itinerary, 'days', None):
                    logger.info(f"[{session.session_id}] Itinerary empty, retrying generation")
                    itinerary = self.builder.build(intent, chosen_dest)

                # If still empty, ask for clarification instead of claiming success
                if not getattr(itinerary, 'days', None):
                    response_text = (
                        f"I attempted to build an itinerary for {chosen_dest.name}, but I couldn't generate a full plan reliably. "
                        "Could you confirm the duration, budget, or provide a clearer destination name?"
                    )
                    session.add_message("Bot", response_text)
                    return {
                        "response": response_text,
                        "type": "clarification",
                        "session_id": session.session_id,
                        "kb_timestamp": session.knowledge_base_timestamp.isoformat(),
                        "refined_query": refined_query
                    }

                # Build a short human-readable summary from the itinerary to include in the reply
                summary_parts = []
                try:
                    if getattr(itinerary, 'days', None):
                        first_day = itinerary.days[0]
                        activities = []
                        for s in getattr(first_day, 'schedule', [])[:3]:
                            if isinstance(s, dict):
                                act = s.get('activity')
                            else:
                                act = getattr(s, 'activity', None)
                            if act:
                                activities.append(act)
                        if activities:
                            summary_parts.append(f"Day 1 highlights: {', '.join(activities)}")
                except Exception:
                    pass

                response_text = f"Perfect! I've built a detailed itinerary for {chosen_dest.name}.\n\n"
                response_text += f"Here's your {intent.duration_days or 2}-day plan with accommodations, packing list, and emergency contacts.\n\n"
                if summary_parts:
                    response_text += "Quick summary:\n" + "\n".join(summary_parts) + "\n\n"

                session.add_message("Bot", response_text)
                session.add_topic(chosen_dest.name)

                # Serialize itinerary safely (support pydantic v2 and v1)
                try:
                    if hasattr(itinerary, 'model_dump'):
                        data_obj = itinerary.model_dump()
                    elif hasattr(itinerary, 'dict'):
                        data_obj = itinerary.dict()
                    else:
                        data_obj = dict(itinerary)
                except Exception:
                    data_obj = {}

                return {
                    "response": response_text,
                    "type": "itinerary",
                    "data": data_obj,
                    "session_id": session.session_id,
                    "kb_timestamp": session.knowledge_base_timestamp.isoformat(),
                    "refined_query": refined_query
                }

        # Suggest destinations
        suggestions = self.suggester.suggest(intent, top_k=5)

        # Find new destination not already suggested
        new_dest = None
        for dest in suggestions.destinations:
            if dest.name not in session.suggested_places:
                new_dest = dest
                break

        if not new_dest:
            new_dest = suggestions.destinations[0]

        # Get enriched description
        description = self.desc_gen.generate(new_dest.name)

        # Build response
        response_text = f"Based on your preferences, I suggest **{new_dest.name}**!\n\n"

        if new_dest.match_score < 40 or "Warning" in new_dest.reasoning:
            response_text += f"{new_dest.reasoning}\n\n"

        response_text += f"{description}\n\n"

        missing = []
        if not intent.budget:
            missing.append("budget")
        if not intent.duration_days:
            missing.append("duration")
        if not intent.interests:
            missing.append("interests")

        if missing:
            response_text += f"To refine further, tell me about your **{', '.join(missing)}**. "

        response_text += f"\n\nWould you like me to build a detailed itinerary for {new_dest.name}?"

        session.add_message("Bot", response_text)
        session.suggested_places.append(new_dest.name)
        session.add_topic(new_dest.name)

        return {
            "response": response_text,
            "type": "suggestion",
            "data": new_dest.model_dump(),
            "suggested_place_name": new_dest.name,
            "session_id": session.session_id,
            "kb_timestamp": session.knowledge_base_timestamp.isoformat(),
            "refined_query": refined_query
        }

    def _handle_general_chat(self,
                            user_input: str,
                            session: ChatSession,
                            intent_decision) -> Dict[str, Any]:
        """Handle general chat with RAG grounding to prevent hallucinations"""

        # Retrieve from KB with source tracking
        rag_results = self.rag.retrieve_with_sources(user_input, top_k=3)
        documents = rag_results["documents"]
        sources = rag_results["sources"]
        facts = rag_results["facts"]
        kb_timestamp = rag_results["kb_timestamp"]

        # Format context for LLM
        context = self.rag.format_context([
            {
                "document": doc,
                "score": score
            }
            for doc, score in zip(documents, rag_results["scores"])
        ])

        # Extract topic from intent keywords
        topic = None
        if intent_decision.extracted_keywords:
            topic = intent_decision.extracted_keywords[0].lower()

        # Generate varied response
        if intent_decision.intent_type == IntentType.DESTINATION_INFO:
            place_name = user_input.split()[-1] if user_input else "destination"
            response_text = self.variation_gen.generate_varied_destination_response(
                place_name,
                documents[0] if documents else {},
                context
            )
        elif intent_decision.intent_type == IntentType.TRAVEL_TIPS:
            response_text = self.variation_gen.generate_varied_tips_response(
                topic or "travel",
                context
            )
        else:
            # General travel chat
            response_text = self._generate_grounded_response(
                user_input,
                context,
                facts
            )

        # Add personalization if user preferences known
        if session.user_preferences:
            response_text = self.variation_gen.add_personal_touch(
                response_text,
                session.user_preferences
            )

        session.add_message("Bot", response_text)
        if topic:
            session.add_topic(topic)

        return {
            "response": response_text,
            "type": "general_chat",
            "sources": sources,
            "facts_used": facts,
            "session_id": session.session_id,
            "kb_timestamp": kb_timestamp
        }

    def _generate_grounded_response(self,
                                   user_input: str,
                                   context: str,
                                   facts: List[Dict[str, str]]) -> str:
        """Generate response grounded in RAG facts only"""

        system_prompt = """You are a knowledgeable travel assistant for trips near Pune.
You MUST only mention facts from the provided knowledge base.
Do NOT invent or hallucinate information about places, costs, or details.

If information is not in the knowledge base, say so clearly:
"I don't have information about that yet, but I'd recommend checking [source]"

Be conversational, helpful, and concise. Keep responses to 3-4 sentences."""

        user_prompt = f"""User question: {user_input}

Knowledge base information:
{context}

Respond based ONLY on the information above. Do not hallucinate."""

        try:
            response = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )
            return response
        except Exception as e:
            return f"I'd like to help with that! Could you rephrase your question? " \
                   f"I specialize in travel near Pune."

    def _handle_out_of_scope(self, user_input: str, session: ChatSession) -> str:
        """Handle queries that are not travel-related"""
        responses = [
            "That's interesting, but I specialize in travel planning! Can I help you with a trip instead?",
            "I'm focused on helping you plan amazing travels. Do you have any travel questions?",
            "I'm your travel assistant! What kind of trip are you thinking about?",
            "That's outside my expertise, but I'd love to help plan your next adventure!"
        ]

        # Rotate responses to avoid repetition
        response_idx = len(session.message_history) % len(responses)
        return responses[response_idx]

    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get summary of a conversation session"""
        if session_id not in self.sessions:
            return None

        session = self.sessions[session_id]
        return {
            "session_id": session_id,
            "created_at": session.created_at.isoformat(),
            "last_message_at": session.last_message_at.isoformat(),
            "message_count": len(session.message_history),
            "topics_discussed": list(session.topics_discussed),
            "suggested_places": session.suggested_places,
            "user_preferences": session.user_preferences
        }

    def end_session(self, session_id: str) -> bool:
        """End a session and clean up memory"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
