"""
M1: Intent Extractor Module
Parses natural language user queries into structured JSON format
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, model_validator
from utils.llm_client import LLMClient


class TravelIntent(BaseModel):
    """Structured travel intent extracted from user query"""
    budget: Optional[Union[int, str]] = Field(None, description="Budget per person in INR")
    group_size: Union[int, str] = Field(1, description="Number of people traveling")
    duration_days: Optional[Union[int, str]] = Field(None, description="Trip duration in days")
    start_date: Optional[str] = Field(None, description="Preferred start date (YYYY-MM-DD)")
    interests: List[str] = Field(default_factory=list, description="Travel interests/preferences")
    avoid_list: List[str] = Field(default_factory=list, description="Things to avoid")
    crowd_preference: Optional[str] = Field(None, description="Crowd preference: low/medium/high/any")
    accommodation_needed: bool = Field(False, description="Whether overnight stay is needed")
    transport_mode: Optional[str] = Field(None, description="Preferred transport: car/bike/bus/any")
    special_requirements: List[str] = Field(default_factory=list, description="Special needs or requirements")
    original_query: str = Field(..., description="Original user query")

    @model_validator(mode='before')
    @classmethod
    def map_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        
        # Aggressive key mapping
        mappings = {
            "budget": ["cost", "price", "max_budget", "estimated_budget", "total_budget"],
            "duration_days": ["duration", "days", "trip_length", "nights"],
            "group_size": ["people", "travelers", "count", "members", "pax"]
        }
        
        for target, alts in mappings.items():
            if target not in data or data[target] is None:
                for alt in alts:
                    if alt in data:
                        data[target] = data[alt]
                        break
        
        # Type cleanup
        if "interests" in data and isinstance(data["interests"], str):
            data["interests"] = [i.strip() for i in data["interests"].split(",")]
            
        return data


class IntentExtractor:
    """
    M1: Intent Extractor
    Converts natural language travel queries into structured JSON
    """
    
    SYSTEM_PROMPT = """You are an expert travel intent extraction system for WanderAI.
Your job is to parse user travel queries and extract structured information.

Extract the following information:
- budget: Per person budget in INR (if mentioned)
- group_size: Number of people (default 1 if not mentioned)
- duration_days: Trip duration in days (weekend = 2, week = 7, etc.)
- start_date: Preferred date in YYYY-MM-DD format (if mentioned)
- interests: List of travel interests (beach, trek, adventure, peaceful, heritage, etc.)
- avoid_list: Things user wants to avoid (crowds, heat, rain, etc.)
- crowd_preference: User's crowd tolerance (low/medium/high/any)
- accommodation_needed: true if overnight stay mentioned
- transport_mode: Preferred transport (car/bike/bus/any)
- special_requirements: Any special needs (elderly-friendly, kid-friendly, wheelchair access, etc.)

Guidelines:
- Be conservative: only extract explicitly mentioned information
- For dates: "this weekend" = next Saturday, "next month" = first day of next month
- For interests: infer from context (e.g., "relaxing" → peaceful, "adventure" → trek/adventure)
- For budget: if range given, use the upper limit
- For group: "friends" without number = assume 4, "family" = assume 4, "couple" = 2

Respond with valid JSON only."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def extract(self, user_query: str) -> TravelIntent:
        """
        Extract structured intent from natural language query
        
        Args:
            user_query: Natural language travel query
        
        Returns:
            TravelIntent object with extracted information
        """
        # Create prompt with examples (few-shot learning)
        prompt = self._create_prompt(user_query)
        
        # Get LLM response in JSON mode
        response = self.llm_client.chat_completion(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Low temperature for consistent extraction
            json_mode=True
        )
        
        # Parse JSON response
        intent_data = self.llm_client.extract_json(response)
        
        # Handle cases where LLM wraps response in a top-level key
        if "travel_intent" in intent_data:
            intent_data = intent_data["travel_intent"]
        elif "intent" in intent_data:
            intent_data = intent_data["intent"]
        
        # Add original query
        intent_data["original_query"] = user_query
        
        # Validate and return as Pydantic model
        return TravelIntent(**intent_data)
    
    def _create_prompt(self, user_query: str) -> str:
        """Create few-shot prompt with examples"""
        examples = """
Example 1:
User: "Plan a weekend trip for 4 friends, budget 3k each, love beaches"
{{"budget": 3000, "group_size": 4, "duration_days": 2, "interests": ["beach"], "crowd_preference": "any", "accommodation_needed": true}}

Example 2:
User: "I want to visit a peaceful place this Saturday, avoid crowds"
{{"group_size": 1, "duration_days": 1, "interests": ["peaceful"], "avoid_list": ["crowds"], "crowd_preference": "low", "accommodation_needed": false}}

Example 3:
User: "Looking for adventure trek near Pune for 2 people, budget 1000 per person, next weekend"
{{"budget": 1000, "group_size": 2, "duration_days": 2, "interests": ["trek", "adventure"], "crowd_preference": "any", "accommodation_needed": true}}

Now extract intent from this query:
User: "{query}"
"""
        return examples.format(query=user_query)
    
    def extract_batch(self, queries: List[str]) -> List[TravelIntent]:
        """Extract intents from multiple queries"""
        return [self.extract(query) for query in queries]


# Convenience function
def quick_extract(query: str) -> Dict[str, Any]:
    """Quick intent extraction without managing extractor instance"""
    extractor = IntentExtractor()
    intent = extractor.extract(query)
    return intent.model_dump()


# Example usage and testing
if __name__ == "__main__":
    print("=== M1: Intent Extractor - Testing ===\n")
    
    extractor = IntentExtractor()
    
    # Test cases
    test_queries = [
        "Plan a weekend trip for 4 friends, budget 3k each, love beaches",
        "I want to visit a peaceful place this Saturday, avoid crowds",
        "Looking for adventure trek near Pune for 2 people, budget 1000 per person",
        "Family trip with kids, need safe place with good food, budget 5000",
        "Solo travel, want to do paragliding, any budget",
        "Group of 6, mix of beach and fort lovers, 2 days, avoid rain"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"Test {i}: {query}")
        try:
            intent = extractor.extract(query)
            print(f"Extracted Intent:")
            print(f"  Budget: ₹{intent.budget or 'Not specified'}")
            print(f"  Group Size: {intent.group_size}")
            print(f"  Duration: {intent.duration_days or 'Not specified'} days")
            print(f"  Interests: {', '.join(intent.interests) or 'None'}")
            print(f"  Avoid: {', '.join(intent.avoid_list) or 'None'}")
            print(f"  Crowd Preference: {intent.crowd_preference or 'Any'}")
            print(f"  Accommodation: {'Yes' if intent.accommodation_needed else 'No'}")
            print()
        except Exception as e:
            print(f"Error: {e}\n")
