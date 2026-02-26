"""
Response Generation and Variation Module
Prevents repetitive responses and ensures variety in general chat mode
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from typing import Optional, List, Dict, Any
from datetime import datetime
from utils.llm_client import LLMClient


class ResponseVariationCache:
    """Track previous responses to avoid repetition"""

    def __init__(self, max_history: int = 10):
        self.response_history: List[Dict[str, Any]] = []
        self.max_history = max_history
        self.topic_history: Dict[str, int] = {}  # Track how many times topics discussed

    def add_response(self, query: str, response: str, topic: Optional[str] = None):
        """Add response to history"""
        self.response_history.append({
            "query": query,
            "response": response,
            "topic": topic,
            "timestamp": datetime.now()
        })

        # Keep only recent history
        if len(self.response_history) > self.max_history:
            self.response_history = self.response_history[-self.max_history:]

        # Track topics
        if topic:
            self.topic_history[topic] = self.topic_history.get(topic, 0) + 1

    def get_topic_count(self, topic: str) -> int:
        """How many times has this topic been discussed?"""
        return self.topic_history.get(topic, 0)

    def is_repeated_query(self, query: str) -> bool:
        """Check if this exact query was just asked"""
        if not self.response_history:
            return False

        # Check last 3 messages
        recent_queries = [h["query"].lower() for h in self.response_history[-3:]]
        return query.lower() in recent_queries

    def get_similar_response(self, topic: str) -> Optional[str]:
        """Get a previous response about this topic to avoid repeating"""
        for item in reversed(self.response_history):
            if item["topic"] == topic:
                return item["response"]
        return None


class ResponseVariationGenerator:
    """
    Generate varied responses to avoid repetition.
    Switches between multiple perspectives/templates.
    """

    # Response templates for destination info
    DESTINATION_TEMPLATES = [
        "description_focused",  # Focus on what makes it special
        "practical_info",       # Focus on logistics (cost, time, best time)
        "experience_focused",   # Focus on the experience/feeling
        "comparison",           # Compare with similar places
        "unique_angle"          # Highlight unique/lesser-known aspects
    ]

    # Response templates for travel tips
    TIP_TEMPLATES = [
        "comprehensive",   # Full detailed answer
        "quick_tips",      # Bullet-point format
        "story_based",     # Answer via example/story
        "pro_advice",      # Expert insider tips
        "safety_focused"   # Focus on safety/best practices
    ]

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
        self.variation_cache = ResponseVariationCache()

    def generate_varied_destination_response(self,
                                            place_name: str,
                                            place_info: Dict[str, Any],
                                            context: str,
                                            template: Optional[str] = None) -> str:
        """
        Generate a varied response about a destination using different perspectives

        Args:
            place_name: Name of the place
            place_info: Place information from KB
            context: RAG context/knowledge base info
            template: Which template to use (auto-selects based on history if None)

        Returns:
            Generated response text
        """
        # Auto-select template based on discussion history
        if template is None:
            topic_count = self.variation_cache.get_topic_count(place_name)
            # Rotate through templates based on how many times we've discussed this
            template = self.DESTINATION_TEMPLATES[topic_count % len(self.DESTINATION_TEMPLATES)]

        system_prompt = f"""You are a travel assistant helping users learn about destinations.
Generate a response about {place_name} using the '{template}' perspective:

- description_focused: Highlight what makes this place special and memorable
- practical_info: Focus on logistics (cost, drive time, best time to visit, accommodation)
- experience_focused: Describe the experience and emotions someone would feel
- comparison: Compare this place to similar destinations nearby
- unique_angle: Share lesser-known, unique aspects that make it worth visiting

Use the provided knowledge base information. Keep response to 3-5 sentences.
Be conversational and engaging."""

        user_prompt = f"""Generate a '{template}' perspective response about {place_name}.

Knowledge base info:
{context}

Place details: {place_info}"""

        try:
            response = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            # Track this response
            self.variation_cache.add_response(
                query=f"Tell me about {place_name}",
                response=response,
                topic=place_name.lower()
            )

            return response
        except Exception as e:
            return f"I'd love to tell you more about {place_name}, but let me get the right information first. " \
                   f"What specific aspects interest you? (Cost, activities, best time to visit, etc.)"

    def generate_varied_tips_response(self,
                                     tip_topic: str,
                                     context: str,
                                     template: Optional[str] = None) -> str:
        """
        Generate varied travel tips responses

        Args:
            tip_topic: What the user is asking about (packing, safety, costs, etc.)
            context: RAG context
            template: Which template to use

        Returns:
            Generated response text
        """
        if template is None:
            topic_count = self.variation_cache.get_topic_count(tip_topic)
            template = self.TIP_TEMPLATES[topic_count % len(self.TIP_TEMPLATES)]

        system_prompt = f"""You are a travel expert providing tips about '{tip_topic}'.
Use the '{template}' format:

- comprehensive: Detailed, thorough answer covering all aspects
- quick_tips: Concise bullet points (3-5 tips)
- story_based: Answer through a travel example/story
- pro_advice: Insider expert tips and tricks
- safety_focused: Emphasize safety and best practices

Use the knowledge base information provided. Keep response concise but helpful."""

        user_prompt = f"""Provide '{template}' answer for: '{tip_topic}'

Knowledge base context:
{context}"""

        try:
            response = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            self.variation_cache.add_response(
                query=f"Tips about {tip_topic}",
                response=response,
                topic=tip_topic.lower()
            )

            return response
        except Exception as e:
            return f"Great question about {tip_topic}! The best approach depends on your specific situation. " \
                   f"Tell me more about what you're planning, and I can give you tailored advice."

    def adapt_previous_response(self,
                               original_response: str,
                               user_refinement: str) -> str:
        """
        Rather than regenerate, adapt a previous response based on user feedback

        Args:
            original_response: Previous response from chatbot
            user_refinement: "More details", "Simpler", "Focus on X", etc.

        Returns:
            Adapted response
        """
        system_prompt = """You are refining a travel assistant's previous response based on user feedback.
Adapt the original response by incorporating the user's request WITHOUT regenerating from scratch.
Make minimal, focused changes. Keep the conversational tone."""

        user_prompt = f"""Original response:
{original_response}

User's refinement request:
{user_refinement}

Adapt the response accordingly:"""

        try:
            response = self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )
            return response
        except Exception as e:
            return original_response  # Fallback to original if adaptation fails

    def add_personal_touch(self, response: str, user_preferences: Dict[str, Any]) -> str:
        """
        Add personalization to a response based on user preferences

        Args:
            response: Base response
            user_preferences: User's stated preferences (budget, group size, interests, etc.)

        Returns:
            Personalized response
        """
        if not user_preferences or all(not v for v in user_preferences.values()):
            return response

        preferences_str = ", ".join([f"{k}: {v}" for k, v in user_preferences.items() if v])

        system_prompt = f"""You are personalizing a travel response for someone with these preferences:
{preferences_str}

Enhance the response by:
1. Adding relevant suggestions for their preferences
2. Mentioning cost/budget implications if applicable
3. Adjusting recommendations for their group size
4. Highlighting activities matching their interests

Keep the response length similar. Be natural and conversational."""

        user_prompt = f"""Original response:
{response}

Personalize for: {preferences_str}"""

        try:
            return self.llm_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )
        except Exception as e:
            return response  # Fallback if personalization fails

    def get_response_variation_level(self) -> str:
        """Get stats on how varied responses have been"""
        if not self.variation_cache.response_history:
            return "fresh"  # No history yet

        avg_topic_uses = sum(self.variation_cache.topic_history.values()) / \
                        len(self.variation_cache.topic_history)

        if avg_topic_uses < 1.5:
            return "highly_varied"
        elif avg_topic_uses < 2.5:
            return "well_varied"
        else:
            return "repetitive"  # Same topics discussed repeatedly


if __name__ == "__main__":
    # Test the response variation generator
    gen = ResponseVariationGenerator()

    # Simulate multiple responses about same topic
    place_info = {
        "name": "Alibaug Beach",
        "category": "beach",
        "cost": "₹500-1000 per person",
        "drive_time": "1.5 hours"
    }

    context = "Alibaug is a popular beach destination near Pune..."

    print("=== Response Variation Demo ===\n")

    for i in range(3):
        print(f"Response {i+1}:")
        response = gen.generate_varied_destination_response(
            "Alibaug Beach",
            place_info,
            context
        )
        print(response)
        print()
