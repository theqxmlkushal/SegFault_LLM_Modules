"""
Routing Engine for WanderAI Chatbot
Intelligently routes user queries to appropriate handlers (modules vs RAG-only)
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel
from utils.llm_client import LLMClient


class IntentType(str, Enum):
    """Types of user intents for routing"""
    TRIP_SUGGESTION = "trip_suggestion"  # "Suggest me places", "What's a good destination?"
    ITINERARY_REQUEST = "itinerary_request"  # "Build my itinerary", "Plan my trip"
    DESTINATION_INFO = "destination_info"  # "Tell me about X place", "What's special about Y?"
    TRAVEL_TIPS = "travel_tips"  # "What should I pack?", "How to travel safely?"
    GENERAL_CHAT = "general_chat"  # General conversation
    OUT_OF_SCOPE = "out_of_scope"  # Questions not travel-related


class RoutingDecision(BaseModel):
    """Decision from routing engine"""
    intent_type: IntentType
    requires_modules: bool  # True if should use M1/M2/M3, False if RAG-only
    confidence: float  # 0-1, how confident about this routing
    extracted_keywords: List[str]  # Keywords that drove this decision
    reasoning: str  # Explanation of routing decision
    path: Optional[str] = None  # CRITICAL: Explicit routing path - "TASK_MODULES", "RAG_ONLY", "FALLBACK"


class RoutingEngine:
    """
    Intelligent router that decides:
    1. What type of query is this?
    2. Should we use task-specific modules (M2/M3) or RAG-only general chat?
    3. Is this out-of-scope?
    """

    # CRITICAL: Confidence thresholds for explicit path routing
    TASK_MODULE_CONFIDENCE_THRESHOLD = 0.65  # Minimum confidence needed for M1-M3 modules
    RAG_ONLY_DEFAULT_CONFIDENCE_THRESHOLD = 0.50  # Minimum for RAG-only responses

    TRIP_SUGGESTION_KEYWORDS = {
        "suggest", "recommend", "best", "where", "destination", "place",
        "options", "alternatives", "choose", "prefer", "like to go",
        "good place", "fun", "weekend", "getaway", "escape",
        "trek", "hike", "hiking", "trekking", "mountain", "beach", "hill"
    }

    ITINERARY_REQUEST_KEYWORDS = {
        "itinerary", "plan", "build", "schedule", "organize", "arrange",
        "day by day", "timeline", "detailed plan", "what to do", "activities",
        "how to spend", "day plan", "activities plan", "full itinerary",
        "trek", "hike", "hiking", "trekking", "organize trip", "plan trip"
    }

    DESTINATION_INFO_KEYWORDS = {
        "tell me about", "what about", "information", "describe", "details",
        "what is", "how is", "famous", "known for", "special", "attractions",
        "things to do", "visit", "see", "explore", "history", "culture"
    }

    TRAVEL_TIPS_KEYWORDS = {
        "tip", "advice", "suggestion", "pack", "carry", "what to bring",
        "safety", "best time", "cost", "budget", "how much", "save money",
        "accommodation", "transport", "food", "climate", "weather", "clothes",
        "documents", "vaccine", "insurance", "guide", "book"
    }

    TRAVEL_RELATED_KEYWORDS = {
        "trip", "travel", "tour", "visit", "vacation", "holiday", "weekend",
        "trek", "hike", "beach", "mountain", "fort", "temple", "city",
        "distance", "road", "drive", "place", "destination", "explore",
        "budget", "cost", "rupees", "money", "day", "night", "person", "people",
        "yes", "no", "ok", "fine", "good", "better", "adjust", "change", "update"
    }

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def classify(self,
                user_input: str,
                conversation_history: Optional[List[Dict[str, str]]] = None) -> RoutingDecision:
        """
        Classify user input and decide routing strategy with EXPLICIT PATH ROUTING.

        Args:
            user_input: Current user message
            conversation_history: Previous messages for context

        Returns:
            RoutingDecision with intent, module requirement, AND explicit path
        """
        # Normalize input
        query_lower = user_input.lower().strip()

        # Step 1: Quick keyword-based routing (fast path)
        # We also pass history to allow follow-ups like "yes", "no", "other"
        quick_decision = self._keyword_based_routing(query_lower, conversation_history)
        
        # Use quick decision if good confidence, otherwise use LLM for nuanced understanding
        # Threshold lowered to 0.70 to accept single-keyword matches like "Plan a trek"
        if quick_decision.confidence >= 0.70:
            decision = quick_decision
        else:
            # Step 2: If not confident or follow-up, use LLM for nuanced understanding
            decision = self._llm_based_routing(user_input, query_lower, conversation_history)

        # CRITICAL: Set explicit routing path based on confidence thresholds
        decision = self._set_routing_path(decision)

        return decision

    def _set_routing_path(self, decision: RoutingDecision) -> RoutingDecision:
        """
        CRITICAL: Enforce explicit routing path based on confidence thresholds

        Routing Logic:
        1. OUT_OF_SCOPE → FALLBACK (reject non-travel)
        2. TRIP_SUGGESTION/ITINERARY → TASK_MODULES (if confidence >= 0.65)
        3. TRIP_SUGGESTION/ITINERARY → FALLBACK (if confidence < 0.65)
        4. DESTINATION_INFO/TRAVEL_TIPS/GENERAL_CHAT → RAG_ONLY
        """
        if decision.intent_type == IntentType.OUT_OF_SCOPE:
            decision.path = "FALLBACK"
            return decision

        # Check if this intent requires task modules
        if decision.intent_type in [IntentType.TRIP_SUGGESTION, IntentType.ITINERARY_REQUEST]:
            if decision.confidence >= self.TASK_MODULE_CONFIDENCE_THRESHOLD:
                # HIGH CONFIDENCE: use task modules
                decision.requires_modules = True
                decision.path = "TASK_MODULES"
                decision.reasoning += f" [✓ Confidence {decision.confidence:.1%} >= {self.TASK_MODULE_CONFIDENCE_THRESHOLD:.0%} threshold]"
            else:
                # LOW CONFIDENCE: fallback to clarification
                decision.requires_modules = False
                decision.path = "FALLBACK"
                decision.reasoning += f" [✗ Confidence {decision.confidence:.1%} < {self.TASK_MODULE_CONFIDENCE_THRESHOLD:.0%} threshold - ask clarification]"
        else:
            # RAG-ONLY intent types (DESTINATION_INFO, TRAVEL_TIPS, GENERAL_CHAT)
            decision.requires_modules = False
            decision.path = "RAG_ONLY"

        return decision

    def _keyword_based_routing(self,
                              query_lower: str,
                              conversation_history: Optional[List[Dict[str, str]]] = None) -> RoutingDecision:
        """Quick routing based on keyword matching"""

        extracted_keywords = []

        # Check for travel-relatedness
        travel_score = sum(1 for kw in self.TRAVEL_RELATED_KEYWORDS if kw in query_lower)
        
        # If no travel keywords in current message, check history to see if we were already in a travel context
        if travel_score == 0 and conversation_history:
            # If the last bot message was about travel, allow short follow-ups like "yes", "ok"
            travel_score = 1 
            reason_suffix = " (inherited from context)"
        else:
            reason_suffix = ""

        if travel_score == 0:
            return RoutingDecision(
                intent_type=IntentType.OUT_OF_SCOPE,
                requires_modules=False,
                confidence=0.9,
                extracted_keywords=[],
                reasoning="Query doesn't contain travel-related keywords"
            )

        # Check specific intent types
        trip_score = sum(1 for kw in self.TRIP_SUGGESTION_KEYWORDS if kw in query_lower)
        itinerary_score = sum(1 for kw in self.ITINERARY_REQUEST_KEYWORDS if kw in query_lower)
        info_score = sum(1 for kw in self.DESTINATION_INFO_KEYWORDS if kw in query_lower)
        tips_score = sum(1 for kw in self.TRAVEL_TIPS_KEYWORDS if kw in query_lower)

        scores = {
            IntentType.TRIP_SUGGESTION: trip_score,
            IntentType.ITINERARY_REQUEST: itinerary_score,
            IntentType.DESTINATION_INFO: info_score,
            IntentType.TRAVEL_TIPS: tips_score
        }

        max_score = max(scores.values())

        # Determine intent based on scores
        # Lowered threshold from > 2 to >= 1 to catch single-keyword intents like "Plan a trek"
        if max_score >= 1:
            # High confidence match
            intent_type = max(scores, key=scores.get)

            # Trip suggestion and itinerary request use modules
            requires_modules = intent_type in [
                IntentType.TRIP_SUGGESTION,
                IntentType.ITINERARY_REQUEST
            ]

            # Improved confidence calculation: factor in the actual score
            # With score 1: confidence ~0.75-0.80, score 2+: 0.85-0.95
            confidence = min(0.70 + (max_score * 0.10), 0.95)

            # Extract matching keywords
            keywords_to_check = {
                IntentType.TRIP_SUGGESTION: self.TRIP_SUGGESTION_KEYWORDS,
                IntentType.ITINERARY_REQUEST: self.ITINERARY_REQUEST_KEYWORDS,
                IntentType.DESTINATION_INFO: self.DESTINATION_INFO_KEYWORDS,
                IntentType.TRAVEL_TIPS: self.TRAVEL_TIPS_KEYWORDS
            }

            extracted_keywords = [
                kw for kw in keywords_to_check[intent_type] if kw in query_lower
            ]

            return RoutingDecision(
                intent_type=intent_type,
                requires_modules=requires_modules,
                confidence=confidence,
                extracted_keywords=extracted_keywords,
                reasoning=f"Matched {intent_type.value} with {max_score} keyword(s)"
            )

        # If no strong match, default to general chat
        return RoutingDecision(
            intent_type=IntentType.GENERAL_CHAT,
            requires_modules=False,
            confidence=0.6,
            extracted_keywords=[],
            reasoning="Travel-related but no specific intent keywords"
        )

    def _llm_based_routing(self,
                          original_input: str,
                          query_lower: str,
                          conversation_history: Optional[List[Dict[str, str]]] = None) -> RoutingDecision:
        """
        Use LLM to make nuanced routing decision when keywords are ambiguous
        """
        system_prompt = """You are a routing expert for a travel chatbot.
Classify the user's intent and decide which handler to use.

Intent types:
1. trip_suggestion: User wants destination suggestions or recommendations
2. itinerary_request: User wants detailed day-by-day travel planning
3. destination_info: User wants information about a specific place
4. travel_tips: User wants travel advice (packing, tips, costs, etc.)
5. general_chat: General conversation (still travel-related)
6. out_of_scope: Not travel-related at all

Module handling:
- trip_suggestion → Use modules (structured extraction needed)
- itinerary_request → Use modules (structured planning needed)
- destination_info → RAG-only (knowledge base retrieval)
- travel_tips → RAG-only (knowledge base retrieval)
- general_chat → RAG-only
- out_of_scope → Clarify or reject

Respond with JSON:
{
  "intent": "one of the above",
  "requires_modules": true/false,
  "confidence": 0.0-1.0,
  "keywords": ["list", "of", "keywords"],
  "reasoning": "brief explanation"
}"""

        # Prepare context
        context = ""
        if conversation_history:
            context = "Recent conversation history:\n"
            for msg in conversation_history[-3:]:
                context += f"{msg.get('role', 'User')}: {msg.get('content', '')}\n"

        user_prompt = f"{context}\nCurrent message: {original_input}"

        try:
            response = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_mode=True
            )

            # Parse LLM response
            data = self.llm_client.extract_json(response)

            intent_str = data.get("intent", "general_chat").lower()

            # Map string to enum
            try:
                intent_type = IntentType(intent_str)
            except ValueError:
                intent_type = IntentType.GENERAL_CHAT

            return RoutingDecision(
                intent_type=intent_type,
                requires_modules=data.get("requires_modules", False),
                confidence=float(data.get("confidence", 0.7)),
                extracted_keywords=data.get("keywords", []),
                reasoning=data.get("reasoning", "LLM classification")
            )

        except Exception as e:
            # Fallback to general chat on LLM failure
            return RoutingDecision(
                intent_type=IntentType.GENERAL_CHAT,
                requires_modules=False,
                confidence=0.5,
                extracted_keywords=[],
                reasoning=f"LLM routing failed: {str(e)}, defaulting to general_chat"
            )


# Example usage
if __name__ == "__main__":
    router = RoutingEngine()

    test_queries = [
        "Suggest me places to visit near Pune for a weekend",
        "Tell me about Alibaug beach",
        "Plan my 5-day trip to the mountains",
        "What should I pack for a trek?",
        "How is the weather in Lonavala?",
        "What's the capital of France?",
        "Build me a detailed itinerary for my honeymoon",
        "Any tips for a first-time traveler?"
    ]

    for query in test_queries:
        decision = router.classify(query)
        print(f"\nQuery: {query}")
        print(f"Intent: {decision.intent_type.value}")
        print(f"Requires Modules: {decision.requires_modules}")
        print(f"Confidence: {decision.confidence:.2f}")
        print(f"Reasoning: {decision.reasoning}")
