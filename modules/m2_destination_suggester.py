"""
M2: Destination Suggester Module
Recommends 3-5 destinations based on user intent using RAG
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator
from utils.llm_client import LLMClient
from utils.rag_engine import SimpleRAG
from modules.m1_intent_extractor import TravelIntent


class Destination(BaseModel):
    """Single destination recommendation"""
    name: str = Field("Unknown Destination", description="Destination name")
    category: str = Field("General", description="Category (beach/fort/trek/etc)")
    match_score: int = Field(70, description="Match score 0-100")
    reasoning: str = Field("Recommended based on your interests", description="Why this destination matches user intent")
    estimated_cost: Union[str, int, Dict[str, Any]] = Field("N/A", description="Estimated cost per person")
    distance: Union[str, int, Dict[str, Any]] = Field("N/A", description="Distance from Pune")
    highlights: List[str] = Field(default_factory=list, description="Key highlights")
    best_for: List[str] = Field(default_factory=list, description="Best suited for")

    @model_validator(mode='before')
    @classmethod
    def handle_nested_data(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return {"reasoning": str(data)}
            
        # Standardize lists
        for field in ["highlights", "best_for"]:
            if field in data and isinstance(data[field], str):
                data[field] = [s.strip() for s in data[field].split(',')]
        
        # Cost/Distance cleanup
        for field in ["estimated_cost", "distance"]:
            if field in data and isinstance(data[field], dict):
                data[field] = data[field].get("value", data[field].get("amount", str(data[field])))
                
        return data


class DestinationSuggestions(BaseModel):
    """Complete destination suggestions response"""
    destinations: List[Destination] = Field(default_factory=list, description="List of recommended destinations")
    summary: str = Field("Here are some great options for your trip.", description="Overall recommendation summary")
    tips: List[str] = Field(default_factory=list, description="General tips for the trip")

    @model_validator(mode='before')
    @classmethod
    def restructure_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        
        # Map common alternative keys
        mappings = {
            "destinations": ["recommendations", "suggestions", "places", "top_picks", "results"],
            "summary": ["overview", "intro", "conclusion"],
            "tips": ["travel_tips", "general_tips", "advice", "guidelines"]
        }
        
        for target, alts in mappings.items():
            if target not in data or not data[target]:
                for alt in alts:
                    if alt in data:
                        data[target] = data[alt]
                        break
        
        # Handle dict-style destinations (mapping names to reasoning/data)
        if "destinations" in data and isinstance(data["destinations"], dict):
            fixed = []
            for name, content in data["destinations"].items():
                if isinstance(content, dict):
                    if "name" not in content: content["name"] = name
                    fixed.append(content)
                else:
                    fixed.append({"name": name, "reasoning": str(content)})
            data["destinations"] = fixed

        return data


class DestinationSuggester:
    """
    M2: Destination Suggester
    Uses RAG to recommend destinations based on user intent
    """
    
    SYSTEM_PROMPT = """You are WanderAI's destination recommendation expert.
Your job is to suggest the best 3-5 destinations near Pune based on user preferences.

You will receive:
1. User's travel intent (structured JSON)
2. Relevant destination information from knowledge base

Your task:
- Analyze user preferences and match with available destinations
- Rank destinations by relevance (match_score 0-100)
- Provide clear reasoning for each recommendation
- Consider: budget, interests, crowd preference, group size, duration
- Be honest: if no perfect match, suggest closest alternatives

Output format: JSON with destinations array, each containing:
- name, category, match_score, reasoning, estimated_cost, distance, highlights, best_for

Also provide:
- summary: 2-3 sentence overview of recommendations
- tips: 3-5 practical tips for their specific trip

Be conversational and helpful in your reasoning."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        rag_engine: Optional[SimpleRAG] = None
    ):
        self.llm_client = llm_client or LLMClient()
        self.rag_engine = rag_engine or SimpleRAG()
    
    def suggest(
        self,
        intent: TravelIntent,
        top_k: int = 5
    ) -> DestinationSuggestions:
        """
        Suggest destinations based on user intent
        
        Args:
            intent: Extracted travel intent
            top_k: Number of destinations to suggest (3-5)
        
        Returns:
            DestinationSuggestions with ranked recommendations
        """
        # Build search query from intent
        search_query = self._build_search_query(intent)
        
        # Retrieve relevant destinations from knowledge base
        context = self.rag_engine.search(search_query, top_k=top_k * 2)  # Get more for filtering
        
        # Create prompt with intent and context
        prompt = self._create_prompt(intent, context)
        
        # Get LLM recommendations
        response = self.llm_client.chat_completion(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            json_mode=True
        )
        
        # Parse and validate response
        suggestions_data = self.llm_client.extract_json(response)
        
        # Limit to top_k destinations
        if len(suggestions_data.get("destinations", [])) > top_k:
            suggestions_data["destinations"] = suggestions_data["destinations"][:top_k]
        
        return DestinationSuggestions(**suggestions_data)
    
    def _build_search_query(self, intent: TravelIntent) -> str:
        """Build search query from intent"""
        query_parts = []
        
        # Add interests
        if intent.interests:
            query_parts.extend(intent.interests)
        
        # Add context based on group size
        if intent.group_size == 1:
            query_parts.append("solo peaceful")
        elif intent.group_size >= 4:
            query_parts.append("group family")
        
        # Add budget context
        if intent.budget and intent.budget < 1000:
            query_parts.append("budget cheap")
        
        # Add crowd preference
        if intent.crowd_preference == "low":
            query_parts.append("peaceful offbeat")
        
        return " ".join(query_parts) if query_parts else "weekend trip"
    
    def _create_prompt(self, intent: TravelIntent, context: str) -> str:
        """Create prompt with intent and RAG context"""
        intent_summary = f"""
User Travel Intent:
- Budget: ₹{intent.budget or 'Flexible'} per person
- Group Size: {intent.group_size} {'person' if intent.group_size == 1 else 'people'}
- Duration: {intent.duration_days or 'Flexible'} days
- Interests: {', '.join(intent.interests) if intent.interests else 'General sightseeing'}
- Avoid: {', '.join(intent.avoid_list) if intent.avoid_list else 'Nothing specific'}
- Crowd Preference: {intent.crowd_preference or 'Any'}
- Accommodation: {'Required' if intent.accommodation_needed else 'Day trip OK'}
- Special Requirements: {', '.join(intent.special_requirements) if intent.special_requirements else 'None'}

Original Query: "{intent.original_query}"
"""
        
        prompt = f"""{intent_summary}

Available Destinations (from knowledge base):
{context}

Based on the user's intent and available destinations, recommend the top 3-5 destinations. 
Rank them by relevance and provide a JSON response summarizing the suggestions.
Include reasoning, match_score, estimated_cost, distance, highlights, and best_for for each.
Plus a summary and a few tips.
"""
        
        return prompt


# Convenience function
def quick_suggest(user_query: str, top_k: int = 3) -> Dict[str, Any]:
    """Quick suggestion without managing instances"""
    from modules.m1_intent_extractor import IntentExtractor
    
    # Extract intent
    extractor = IntentExtractor()
    intent = extractor.extract(user_query)
    
    # Get suggestions
    suggester = DestinationSuggester()
    suggestions = suggester.suggest(intent, top_k)
    
    return suggestions.model_dump()


# Example usage and testing
if __name__ == "__main__":
    print("=== M2: Destination Suggester - Testing ===\n")
    
    from modules.m1_intent_extractor import IntentExtractor
    
    extractor = IntentExtractor()
    suggester = DestinationSuggester()
    
    # Test cases
    test_queries = [
        "Plan a weekend trip for 4 friends, budget 3k each, love beaches",
        "I want to visit a peaceful place this Saturday, avoid crowds",
        "Looking for adventure trek near Pune for 2 people, budget 1000 per person"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"Test {i}: {query}")
        print("-" * 80)
        
        try:
            # Extract intent
            intent = extractor.extract(query)
            print(f"Intent: {intent.interests}, Budget: ₹{intent.budget}, Group: {intent.group_size}\n")
            
            # Get suggestions
            suggestions = suggester.suggest(intent, top_k=3)
            
            print(f"Summary: {suggestions.summary}\n")
            
            print("Recommended Destinations:")
            for j, dest in enumerate(suggestions.destinations, 1):
                print(f"\n{j}. {dest.name} ({dest.category})")
                print(f"   Match Score: {dest.match_score}/100")
                print(f"   Distance: {dest.distance}")
                print(f"   Cost: {dest.estimated_cost}")
                print(f"   Why: {dest.reasoning}")
                if dest.highlights:
                    print(f"   Highlights: {', '.join(dest.highlights)}")
            
            if suggestions.tips:
                print(f"\nTips:")
                for tip in suggestions.tips:
                    print(f"  • {tip}")
            
            print("\n" + "=" * 80 + "\n")
            
        except Exception as e:
            print(f"Error: {e}\n")
