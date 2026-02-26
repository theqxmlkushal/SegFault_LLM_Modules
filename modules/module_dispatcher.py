"""
Module dispatcher: centralizes module invocation and enforces pre/post checks

This dispatcher is intentionally minimal: it delegates to the engine's
existing module instances (QueryRefiner, IntentExtractor, etc.) and
applies a confirmatory intent extraction step before running task modules.
"""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ModuleDispatcher:
    """Central dispatcher to call task modules in a controlled way."""

    def __init__(self, engine: Any):
        # Hold a reference to the engine so we can use its instantiated modules
        self.engine = engine

    def dispatch(self, user_input: str, session: Any, routing_decision: Any) -> Dict[str, Any]:
        """Dispatch to appropriate module pipeline according to routing decision.

        This method mirrors the previous in-engine pipeline but centralizes
        the flow and adds a confirmatory extraction step to reduce wrong
        module invocations.
        """
        logger.debug(f"[{session.session_id}] ModuleDispatcher.dispatch start")

        # M0: refine (use structured refiner if available)
        try:
            structured = self.engine.query_refiner.refine_structured(
                user_input,
                session.message_history[-5:] if session.message_history else []
            )
            refined_query = structured.get("refined")
            flags = structured.get("flags", {})
        except Exception:
            # Fallback to legacy string refine()
            refined_query = self.engine.query_refiner.refine(
                user_input,
                session.message_history[-5:] if session.message_history else []
            )
            flags = {"critical_budget": "[CRITICAL BUDGET CONSTRAINT" in str(refined_query)}

        # Short-circuit: if query refiner flagged an impossible budget, return direct message
        if flags.get("critical_budget"):
            logger.info(f"{session.session_id} Critical budget detected in refined query; short-circuiting module pipeline.")
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
                "data": {"reason": "critical_budget"}
            }

        # M1: intent extraction (confirmatory)
        try:
            intent = self.engine.intent_extractor.extract(refined_query)
        except Exception as e:
            logger.debug(f"Intent extraction failed: {e}")
            return self.engine._handle_fallback(session, routing_decision)

        # If extractor returned falsy result, ask for clarification
        if not intent:
            logger.debug("Intent extractor returned no intent; falling back")
            return self.engine._handle_fallback(session, routing_decision)

        # Route to specific modules
        if routing_decision.intent_type.name == 'TRIP_SUGGESTION':
            try:
                suggestions = self.engine.destination_suggester.suggest(intent, top_k=3)
                if suggestions and getattr(suggestions, 'destinations', None):
                    response_text = self.engine._format_suggestion_response(suggestions)
                    # Serialize Pydantic model safely (support pydantic v2 `model_dump` or v1 `dict`)
                    if hasattr(suggestions, 'model_dump'):
                        data_obj = suggestions.model_dump()
                    elif hasattr(suggestions, 'dict'):
                        data_obj = suggestions.dict()
                    else:
                        try:
                            data_obj = dict(suggestions)
                        except Exception:
                            data_obj = {}

                    return {
                        "response": response_text,
                        "has_answer": True,
                        "sources": ["places.json"],
                        "module_used": "modules",
                        "confidence": routing_decision.confidence,
                        "validation_status": "grounded",
                        "path": "TASK_MODULES",
                        "type": "suggestion",
                        "data": data_obj
                    }
                else:
                    return {
                        "response": "I couldn't find suitable destinations matching your preferences.",
                        "has_answer": False,
                        "sources": [],
                        "module_used": "modules",
                        "confidence": routing_decision.confidence,
                        "validation_status": "partial",
                        "path": "TASK_MODULES",
                        "type": "suggestion",
                        "data": {}
                    }
            except Exception as e:
                logger.exception(f"Destination suggester error: {e}")
                return self.engine._handle_fallback(session, routing_decision)

        elif routing_decision.intent_type.name == 'ITINERARY_REQUEST':
            try:
                destination = self.engine._extract_destination_from_context(session, intent)
                if destination:
                    itinerary = self.engine.itinerary_builder.build(intent, destination)
                    response_text = self.engine._format_itinerary_response(itinerary)

                    # Serialize Itinerary (pydantic v2/v1 compatible)
                    if hasattr(itinerary, 'model_dump'):
                        it_data = itinerary.model_dump()
                    elif hasattr(itinerary, 'dict'):
                        it_data = itinerary.dict()
                    else:
                        try:
                            it_data = dict(itinerary)
                        except Exception:
                            it_data = {}

                    return {
                        "response": response_text,
                        "has_answer": True,
                        "sources": ["places.json"],
                        "module_used": "modules",
                        "confidence": routing_decision.confidence,
                        "validation_status": "grounded",
                        "path": "TASK_MODULES",
                        "type": "itinerary",
                        "data": it_data
                    }
                else:
                    return self.engine._handle_fallback(session, routing_decision)
            except Exception as e:
                logger.exception(f"Itinerary builder error: {e}")
                return self.engine._handle_fallback(session, routing_decision)

        else:
            logger.debug("Routing decision not for task modules; falling back to engine handling")
            return self.engine._handle_fallback(session, routing_decision)
