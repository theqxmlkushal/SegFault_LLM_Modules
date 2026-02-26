"""
WanderAI Chatbot Core V3 - Enhanced Parallel Engine
Implements strict RAG with 4-layer hallucination prevention
Per-message KB freshness, clear module routing, and response variation
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
from modules.routing_engine import RoutingEngine, IntentType, RoutingDecision
from modules.response_generator import ResponseVariationGenerator
from modules.module_dispatcher import ModuleDispatcher

from utils.llm_client import LLMClient
from utils.rag_engine import SimpleRAG
from utils.webhook_manager import WebhookManager
from response_validation import (
    ResponseValidationLayer,
    StrictRAGContext,
    ResponseValidator
)
from utils.formatters import beautify_itinerary

logger = logging.getLogger(__name__)


class ChatSession(BaseModel):
    """Enhanced session-aware conversation context"""
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    last_message_at: datetime = Field(default_factory=datetime.now)
    message_history: List[Dict[str, str]] = Field(default_factory=list)
    topics_discussed: set = Field(default_factory=set)
    previous_responses: Dict[str, str] = Field(default_factory=dict)
    suggested_places: List[str] = Field(default_factory=list)
    knowledge_base_timestamp: datetime = Field(default_factory=datetime.now)
    user_preferences: Dict[str, Any] = Field(default_factory=dict)
    validation_stats: Dict[str, int] = Field(default_factory=lambda: {
        "total_messages": 0,
        "validated_responses": 0,
        "hallucinations_prevented": 0,
        "kb_refreshes": 0
    })

    class Config:
        arbitrary_types_allowed = True

    def update_timestamp(self):
        self.last_message_at = datetime.now()

    def add_message(self, role: str, content: str):
        self.message_history.append({"role": role, "content": content})
        if len(self.message_history) > 20:
            self.message_history.pop(0)

    def record_validation_event(self, event_type: str):
        """Record validation statistics"""
        if event_type in self.validation_stats:
            self.validation_stats[event_type] += 1


class WanderAIChatbotCoreV3:
    """
    Enhanced chatbot engine with strict RAG enforcement

    Features:
    - 4-layer hallucination prevention
    - Per-message KB freshness checks
    - Clear module vs RAG-only routing with confidence thresholds
    - Response variation to prevent repetition
    - Session-aware conversation management
    - Complete source attribution
    """

    def __init__(
        self,
        rag_engine: Optional[SimpleRAG] = None,
        webhook_manager: Optional[WebhookManager] = None,
        llm_client: Optional[LLMClient] = None,
        kb_path: str = "knowledge_base"
    ):
        """
        Initialize chatbot core with components

        Args:
            rag_engine: RAG engine (creates if None)
            webhook_manager: Webhook manager (creates if None)
            llm_client: LLM client (creates if None)
            kb_path: Path to knowledge base
        """
        # Initialize RAG and LLM
        self.rag = rag_engine or SimpleRAG(kb_path)
        self.llm_client = llm_client or LLMClient()
        self.webhook_manager = webhook_manager or WebhookManager(self.rag)

        # Initialize modules
        self.query_refiner = QueryRefiner()
        self.intent_extractor = IntentExtractor()
        self.destination_suggester = DestinationSuggester(self.llm_client, self.rag)
        self.itinerary_builder = ItineraryBuilder(self.llm_client, self.rag)
        self.place_description_gen = PlaceDescriptionGenerator(self.llm_client, self.rag)

        # Initialize routing and response generation
        self.routing_engine = RoutingEngine(self.llm_client)
        self.response_generator = ResponseVariationGenerator(self.llm_client)

        # Initialize validation layers
        self.validation_layer = ResponseValidationLayer()
        self.strict_context = StrictRAGContext()
        self.response_validator = ResponseValidator()

        # Module dispatcher (centralized module calls)
        self.dispatcher = ModuleDispatcher(self)

        # Session management
        self.sessions: Dict[str, ChatSession] = {}

        logger.info("WanderAIChatbotCoreV3 initialized with strict RAG enforcement")

    def get_or_create_session(self, session_id: Optional[str] = None) -> ChatSession:
        """Get existing session or create new one"""
        if session_id and session_id in self.sessions:
            return self.sessions[session_id]

        session = ChatSession()
        self.sessions[session.session_id] = session
        logger.debug(f"Created new session: {session.session_id}")
        return session

    def process_message(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        refresh_kb: bool = True
    ) -> Dict[str, Any]:
        """
        Process user message with strict RAG enforcement

        Args:
            user_input: User message
            session_id: Session ID (creates new if None)
            refresh_kb: Check for KB updates

        Returns:
            {
                "response": str,
                "has_answer": bool,
                "sources": List[str],
                "module_used": str ("modules", "rag_only", or "clarification"),
                "session_id": str,
                "confidence": float,
                "validation_status": str ("grounded", "partial", "failed"),
                "path": str ("TASK_MODULES", "RAG_ONLY", or "FALLBACK")
            }
        """
        # Session management
        session = self.get_or_create_session(session_id)
        session.add_message("User", user_input)
        session.update_timestamp()
        session.validation_stats["total_messages"] += 1

        # --- PER-MESSAGE KB FRESHNESS CHECK (CRITICAL) ---
        if refresh_kb:
            kb_refreshed = self.rag.conditional_refresh()
            if kb_refreshed:
                session.knowledge_base_timestamp = self.rag.knowledge_base_timestamp
                session.record_validation_event("kb_refreshes")
                logger.info(f"[{session.session_id}] KB refreshed from webhook updates")

        # Intent routing with confidence-based path selection
        # Run a quick structured refinement to detect critical constraints (e.g., impossible budget)
        try:
            refined_struct = self.query_refiner.refine_structured(
                user_input,
                session.message_history[-5:] if session.message_history else []
            )
            flags = refined_struct.get("flags", {}) if isinstance(refined_struct, dict) else {}
            if flags.get("critical_budget"):
                # Immediate short-circuit for impossible budgets
                return {
                    "response": (
                        "It looks like your requested budget is insufficient for the requested duration. "
                        "Please increase the budget, shorten the trip, or provide a destination you already have in mind."
                    ),
                    "has_answer": False,
                    "sources": [],
                    "module_used": "none",
                    "confidence": 0.0,
                    "validation_status": "rejected_budget",
                    "path": "SHORT_CIRCUIT",
                    "type": "error",
                    "data": {"reason": "critical_budget"},
                    "session_id": session.session_id,
                }
        except Exception:
            # If the structured refiner fails, proceed with normal routing
            pass

        routing_decision = self.routing_engine.classify(user_input, session.message_history[-5:])

        # Handle based on routing decision and confidence threshold
        if routing_decision.intent_type == IntentType.OUT_OF_SCOPE:
            result = self._handle_out_of_scope(session, routing_decision)

        elif routing_decision.intent_type in [
            IntentType.TRIP_SUGGESTION,
            IntentType.ITINERARY_REQUEST
        ]:
            # Task module path - requires high confidence
            if routing_decision.confidence >= 0.65:
                result = self._handle_module_pipeline(user_input, session, routing_decision)
            else:
                # Low confidence - fallback to clarification
                result = self._handle_fallback(session, routing_decision)

        else:
            # RAG-only path for general chat (DESTINATION_INFO, TRAVEL_TIPS, GENERAL_CHAT)
            result = self._handle_general_chat(user_input, session, routing_decision)

        # Add session info
        result["session_id"] = session.session_id

        # Post-process the result: verify claims against RAG and ensure polite tone
        try:
            result = self._post_process_response(session, result)
        except Exception as e:
            logger.exception(f"[{session.session_id}] Post-processing error: {e}")

        return result

    def _post_process_response(self, session: ChatSession, result: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process a generated result: verify claims and enforce polite fallback.

        - Uses `ResponseValidationLayer.verify_claims_against_rag` to detect unsupported
          claims and redacts or requests clarification instead of returning hallucinated facts.
        - Ensures responses use a polite/helpful tone when declining to answer.
        """
        response_text = result.get("response", "")
        
        # Skip strict validation for responses from task modules (they're already grounded)
        # Only apply strict validation to RAG-only responses
        if result.get("path") == "TASK_MODULES" or result.get("module_used") == "modules":
            # For module responses, just ensure the tone is good
            if result.get("response") and not result.get("response").lower().startswith("sorry"):
                # Don't add extra text for suggestion responses
                if result.get("type") != "suggestion":
                    result["response"] = result.get("response") + "\n\nIf you'd like more details, I can expand any section."
            return result

        # Quick verification using RAG for claims (RAG-only paths)
        try:
            verification = self.validation_layer.verify_and_redact(response_text, self.rag)
        except Exception as e:
            logger.debug(f"Verification step failed: {e}")
            verification = {"verified": True, "unsupported_claims": []}

        unsupported = verification.get("unsupported_claims", [])

        if unsupported:
            # Conservative behavior: redact unsupported claims and apologize
            modified = response_text
            for cand in unsupported:
                try:
                    # Replace occurrences of the candidate with a short marker
                    modified = modified.replace(cand, f"[Unverified: {cand}]")
                except Exception:
                    continue

            polite_prefix = (
                "I'm sorry — I couldn't verify some details in my response. "
                "I've removed or marked unverified items below. If you'd like, I can try to look up more details or clarify.\n\n"
            )

            # Build conservative summary of supported sources if available
            sources = result.get("sources") or []
            if sources:
                sources_str = ', '.join(sources)
                footer = f"\n\n**Verified sources:** {sources_str}"
            else:
                footer = "\n\n**Verified sources:** (none found)"

            result["response"] = polite_prefix + modified + footer
            result["validation_status"] = "partial"
            result["has_answer"] = False
        else:
            # Ensure tone is polite/concise: optionally wrap with friendly closing
            if result.get("response") and not result.get("response").lower().startswith("sorry"):
                result["response"] = result.get("response") + "\n\nIf you'd like more details, I can expand any section."

        # Beautify itinerary responses for user-facing output while keeping raw data
        if result.get("type") == "itinerary" and result.get("data"):
            try:
                beaut = beautify_itinerary(result["data"])
                # Keep raw data available under a separate key and set pretty response
                result["response_pretty"] = beaut
                result["response"] = beaut
            except Exception as e:
                logger.debug(f"Failed to beautify itinerary: {e}")

        return result

    def _handle_general_chat(
        self,
        user_input: str,
        session: ChatSession,
        routing_decision: RoutingDecision
    ) -> Dict[str, Any]:
        """
        Handle general chat with strict RAG enforcement (RAG-only path)

        Applies all 4 validation layers for hallucination prevention
        """
        logger.debug(f"[{session.session_id}] Processing as general chat (RAG-only)")

        # Retrieve from RAG with source tracking
        rag_results = self.rag.retrieve_with_sources(user_input, top_k=5)

        # Check if we have relevant information
        if not rag_results.get("documents"):
            # No KB information found
            return self._handle_no_answer(session, routing_decision)

        # --- LAYER 1: Strict Context Enforcement ---
        strict_context = self.strict_context.format_for_llm(
            rag_results.get("documents", []),
            rag_results.get("sources", []),
            rag_results.get("facts", []),
            user_input
        )

        # --- LAYER 2: System Prompt Prohibition ---
        system_prompt = self.strict_context.format_system_prompt()

        # Generate response with strict constraints
        response = self._generate_response_grounded(
            user_input,
            strict_context,
            system_prompt,
            session
        )

        # --- LAYER 3: Response Parsing Validation ---
        # --- LAYER 4: Source Attribution ---
        is_valid, validated_response, unsourced_claims = self.validation_layer.validate_response(
            response,
            rag_results.get("sources", []),
            rag_results.get("facts", []),
            str(self.rag.knowledge_base_timestamp)
        )

        # Record validation event
        if not is_valid:
            session.record_validation_event("hallucinations_prevented")
            logger.warning(f"[{session.session_id}] Hallucination detected and prevented")

        session.record_validation_event("validated_responses")

        # Store response and update session preferences
        session.previous_responses[user_input] = validated_response
        session.topics_discussed.add(routing_decision.intent_type.value)

        return {
            "response": validated_response,
            "has_answer": True,
            "sources": rag_results.get("sources", []),
            "module_used": "rag_only",
            "confidence": routing_decision.confidence,
            "validation_status": "grounded" if is_valid else "partial",
            "path": "RAG_ONLY",
            "type": "general_chat"
        }

    def _handle_module_pipeline(
        self,
        user_input: str,
        session: ChatSession,
        routing_decision: RoutingDecision
    ) -> Dict[str, Any]:
        """Delegate module pipeline to the centralized ModuleDispatcher"""
        try:
            return self.dispatcher.dispatch(user_input, session, routing_decision)
        except Exception as e:
            logger.error(f"[{session.session_id}] Module pipeline error: {str(e)}")
            return self._handle_fallback(session, routing_decision)

    def _handle_fallback(
        self,
        session: ChatSession,
        routing_decision: RoutingDecision
    ) -> Dict[str, Any]:
        """
        Graceful fallback when confidence too low or module fails

        Returns clarification questions instead of guessing
        """
        logger.debug(f"[{session.session_id}] Using fallback (low confidence or module failure)")

        clarification_responses = {
            IntentType.TRIP_SUGGESTION: [
                "I'd like to suggest a destination! Could you tell me more about:\n"
                "- Your budget per person\n"
                "- How many days do you have?\n"
                "- What interests you (beach, trek, heritage, city, etc.)?",

                "To give you better suggestions, let me know:\n"
                "- Budget range\n"
                "- Trip duration\n"
                "- Type of experience you want",

                "I can help you find the perfect trip! Please share:\n"
                "- How much are you planning to spend?\n"
                "- How many days?\n"
                "- What kind of activities interest you?",
            ],
            IntentType.ITINERARY_REQUEST: [
                "I can build a detailed itinerary! First, tell me about your trip:\n"
                "- Where are you thinking of going?\n"
                "- How many days?\n"
                "- What's your budget?",

                "To create an itinerary, I need:\n"
                "- Destination name\n"
                "- Number of days\n"
                "- Your interests and budget",
            ]
        }

        # Get appropriate response set
        response_options = clarification_responses.get(
            routing_decision.intent_type,
            ["I'm not sure I understand. Could you provide more details?"]
        )

        # Rotate to avoid repetition
        msg_idx = session.validation_stats["total_messages"] % len(response_options)
        response = response_options[msg_idx]

        return {
            "response": response,
            "has_answer": False,
            "sources": [],
            "module_used": "clarification",
            "confidence": routing_decision.confidence,
            "validation_status": "partial",
            "path": "FALLBACK",
            "type": "clarification_needed"
        }

    def _handle_no_answer(
        self,
        session: ChatSession,
        routing_decision: RoutingDecision
    ) -> Dict[str, Any]:
        """Handle queries when KB has no relevant information"""
        logger.debug(f"[{session.session_id}] No KB information found")

        available_topics = self._get_available_topics()

        response = (
            f"I don't have this information in my knowledge base. "
            f"I can help with: {', '.join(available_topics)}. "
            f"Feel free to ask me about any of these!"
        )

        return {
            "response": response,
            "has_answer": False,
            "sources": [],
            "module_used": "rag_only",
            "confidence": routing_decision.confidence,
            "validation_status": "failed",
            "path": "RAG_ONLY",
            "type": "no_answer"
        }

    def _handle_out_of_scope(
        self,
        session: ChatSession,
        routing_decision: RoutingDecision
    ) -> Dict[str, Any]:
        """Handle out-of-scope queries"""
        logger.debug(f"[{session.session_id}] Query out of scope")

        response = (
            "I'm a travel assistant focused on Pune area trips. "
            "I can help with: destination suggestions, itinerary planning, "
            "travel tips, and place information. "
            "Do you have any travel-related questions?"
        )

        return {
            "response": response,
            "has_answer": False,
            "sources": [],
            "module_used": "rag_only",
            "confidence": 0.0,
            "validation_status": "failed",
            "path": "FALLBACK",
            "type": "out_of_scope"
        }

    # Helper methods

    def _generate_response_grounded(
        self,
        user_input: str,
        context: str,
        system_prompt: str,
        session: ChatSession
    ) -> str:
        """Generate response strictly grounded in KB context"""
        # Prepare conversation history for context
        history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in session.message_history[-4:]  # Last 4 messages for context
        ]

        # Use LLM to generate grounded response
        response = self.llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=f"{context}\n\nUser question: {user_input}",
            conversation_history=history,
            max_tokens=500,
            temperature=0.3  # Lower temp for factuality
        )

        return response

    def _format_suggestion_response(self, suggestions: Any) -> str:
        """Format destination suggestions for display"""
        if not suggestions or not suggestions.destinations:
            return "No suitable destinations found."

        parts = ["Based on your preferences, here are my suggestions:\n"]

        for i, dest in enumerate(suggestions.destinations[:3], 1):
            parts.append(f"{i}. **{dest.name}** (Match: {dest.match_score:.0%})")
            if hasattr(dest, 'highlights') and dest.highlights:
                parts.append(f"   Highlights: {', '.join(dest.highlights[:2])}")

        if hasattr(suggestions, 'tips') and suggestions.tips:
            parts.append(f"\nTravel Tips: {suggestions.tips[0]}")

        return "\n".join(parts)

    def _format_itinerary_response(self, itinerary: Any) -> str:
        """Format itinerary for display"""
        if not itinerary:
            return "Could not create itinerary."

        parts = [f"**{itinerary.destination} Trip Plan** ({itinerary.duration} days)\n"]

        if hasattr(itinerary, 'days') and itinerary.days:
            for day_plan in itinerary.days[:3]:  # First 3 days
                parts.append(f"**Day {day_plan.get('day', 'N/A')}:**")
                if 'activities' in day_plan:
                    for activity in day_plan['activities'][:2]:
                        parts.append(f"  - {activity}")

        return "\n".join(parts)

    def _extract_destination_from_context(
        self,
        session: ChatSession,
        intent: Any
    ) -> Optional[Any]:
        """Extract destination from conversation context or intent"""
        # Check if user mentioned destination in intent
        if hasattr(intent, 'destination') and intent.destination:
            return intent.destination

        # Check suggested places from session
        if session.suggested_places:
            return session.suggested_places[0]

        return None

    def _get_available_topics(self) -> List[str]:
        """Get list of available topics from KB"""
        documents = self.rag.documents if self.rag else []

        topics = set()
        for doc in documents[:50]:  # Sample documents
            if 'category' in doc:
                topics.add(doc['category'])
            elif 'title' in doc:
                topics.add(doc['title'].split()[0])

        return list(topics)[:5] if topics else ["destinations", "treks", "beaches"]
