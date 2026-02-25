"""
M3: Itinerary Builder Module
Creates detailed day-by-day travel itineraries
"""
import sys
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator

sys.path.append(str(Path(__file__).parent.parent))

from utils.llm_client import LLMClient
from utils.rag_engine import SimpleRAG
from modules.m1_intent_extractor import TravelIntent
from modules.m2_destination_suggester import Destination

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TimeSlot(BaseModel):
    """Single time slot in itinerary"""
    time: str = Field("Anytime", description="Time (e.g., '09:00 AM')")
    activity: str = Field("Sightseeing", description="Activity description")
    location: str = Field("Local Area", description="Location name")
    duration: str = Field("Flexible", description="Estimated duration")
    cost: Optional[Union[str, int]] = Field(None, description="Estimated cost")
    tips: Optional[str] = Field(None, description="Specific tips for this activity")

    @model_validator(mode='before')
    @classmethod
    def handle_short_form(cls, v: Any) -> Any:
        if isinstance(v, str):
            return {"activity": v}
        return v


class DayPlan(BaseModel):
    """Single day itinerary"""
    day: int = Field(1, description="Day number")
    title: str = Field("Day Plan", description="Day title/theme")
    schedule: List[TimeSlot] = Field(default_factory=list, description="Time-based schedule")
    meals: Dict[str, str] = Field(default_factory=dict, description="Meal recommendations")
    total_cost: Union[str, int] = Field("TBD", description="Estimated total cost for the day")
    notes: Optional[str] = Field(None, description="Additional notes for the day")

    @model_validator(mode='before')
    @classmethod
    def ensure_basics(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return {"title": str(data)}
        
        # Ensure schedule is always a list
        if "schedule" in data and isinstance(data["schedule"], dict):
            slots = [{"time": t, "activity": str(a)} for t, a in data["schedule"].items()]
            data["schedule"] = slots
        elif "schedule" not in data:
            data["schedule"] = []
            
        return data


class Itinerary(BaseModel):
    """Complete travel itinerary"""
    destination: str = Field("Destination", description="Main destination")
    duration: int = Field(1, description="Total days")
    days: List[DayPlan] = Field(default_factory=list, description="Day-by-day plans")
    total_estimated_cost: Union[str, int] = Field("TBD", description="Total trip cost estimate")
    packing_list: List[str] = Field(default_factory=list, description="Recommended items to pack")
    important_notes: List[str] = Field(default_factory=list, description="Important information")
    emergency_contacts: Dict[str, str] = Field(default_factory=dict, description="Emergency contact numbers")

    @field_validator('duration', mode='before')
    @classmethod
    def parse_duration(cls, v: Any) -> int:
        if isinstance(v, int): return v
        if isinstance(v, str):
            # Extract first number found in string (e.g., "1 day" -> 1, "3d" -> 3)
            match = re.search(r'\d+', v)
            if match: return int(match.group())
            
            # Handle text numbers
            text_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
            for word, val in text_map.items():
                if word in v.lower(): return val
        return 1

    @model_validator(mode='before')
    @classmethod
    def restructure_itinerary(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
            
        # 1. Handle wrappers and key mapping
        mappings = {
            "total_estimated_cost": ["total_cost", "cost", "budget"],
            "days": ["itinerary_details", "schedule", "plan", "details"],
            "destination": ["place", "location"],
            "duration": ["days_count", "length"]
        }
        
        # Unwrap "itinerary" if it exists
        if "itinerary" in data and isinstance(data["itinerary"], dict):
            it_data = data["itinerary"]
            for k, v in it_data.items():
                if k not in data or not data[k]:
                    data[k] = v

        for target, alts in mappings.items():
            if target not in data or not data[target]:
                for alt in alts:
                    if alt in data:
                        data[target] = data[alt]
                        break

        # 2. Extract root-level DayN keys
        if ("days" not in data or not data["days"]) and any(re.match(r'^day\s*\d+', k.lower()) for k in data.keys()):
            items = []
            for k, v in data.items():
                if re.match(r'^day\s*\d+', k.lower()) and isinstance(v, dict):
                    match = re.search(r'\d+', k)
                    items.append((int(match.group()) if match else 99, v))
            if items:
                items.sort(key=lambda x: x[0])
                data["days"] = [x[1] for x in items]
                for i, d in enumerate(data["days"], 1):
                    if "day" not in d: d["day"] = i

        return data

    @field_validator('packing_list', 'important_notes', mode='before')
    @classmethod
    def ensure_list(cls, v: Any) -> List[str]:
        if isinstance(v, str): return [s.strip() for s in v.split(',')]
        if isinstance(v, list): return [str(i) for i in v]
        return []

    @field_validator('emergency_contacts', mode='before')
    @classmethod
    def ensure_dict(cls, v: Any) -> Dict[str, str]:
        if isinstance(v, list): return {f"Contact {i+1}": str(item) for i, item in enumerate(v)}
        if isinstance(v, str): return {"Info": v}
        return v if isinstance(v, dict) else {}


class ItineraryBuilder:
    """
    M3: Itinerary Builder
    Creates detailed day-by-day travel plans
    """
    
    SYSTEM_PROMPT = """You are WanderAI's itinerary planning expert.
Your job is to create detailed, practical day-by-day travel itineraries.
Ensure the response is a valid JSON object."""

    def __init__(self, llm_client: Optional[LLMClient] = None, rag_engine: Optional[SimpleRAG] = None):
        self.llm_client = llm_client or LLMClient()
        self.rag_engine = rag_engine or SimpleRAG()
    
    def build(self, intent: TravelIntent, destination: Destination, ml_data: Optional[Dict[str, Any]] = None) -> Itinerary:
        """Build detailed itinerary for chosen destination"""
        context = self.rag_engine.search(f"{destination.name} details", top_k=2)
        prompt = self._create_prompt(intent, destination, context, ml_data)
        
        response = self.llm_client.chat_completion(
            messages=[{"role": "system", "content": self.SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            temperature=0.7, json_mode=True
        )
        
        itinerary_data = self.llm_client.extract_json(response)
        
        # Inject defaults from inputs
        if "destination" not in itinerary_data: itinerary_data["destination"] = destination.name
        if "duration" not in itinerary_data: itinerary_data["duration"] = getattr(intent, 'duration_days', 1) or 1
            
        try:
            return Itinerary(**itinerary_data)
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return Itinerary.model_validate(itinerary_data, strict=False)
    
    def _create_prompt(self, intent: TravelIntent, destination: Destination, context: str, ml_data: Optional[Dict[str, Any]]) -> str:
        ml_context = f"\nML Insights: {ml_data}" if ml_data else ""
        return f"""
Create a {intent.duration_days or 2}-day itinerary for {destination.name}.
Budget: {intent.budget or 'Flexible'}, Group: {intent.group_size}, Interests: {', '.join(intent.interests)}

Context: {context} {ml_context}

Return JSON with: destination, duration, days (list with schedule), total_estimated_cost, packing_list, important_notes, emergency_contacts.
"""


def quick_build(user_query: str, destination_index: int = 0) -> Dict[str, Any]:
    from modules.m1_intent_extractor import IntentExtractor
    from modules.m2_destination_suggester import DestinationSuggester
    
    intent = IntentExtractor().extract(user_query)
    suggestions = DestinationSuggester().suggest(intent, top_k=3)
    itinerary = ItineraryBuilder().build(intent, suggestions.destinations[destination_index])
    
    return itinerary.model_dump()


if __name__ == "__main__":
    print("=== M3: Itinerary Builder - Simplified Testing ===\n")
    try:
        res = quick_build("Plan a trip to Alibaug for 2 friends, budget 5k")
        print(f"Itinerary for {res['destination']} built successfully!")
    except Exception as e:
        print(f"Error: {e}")
