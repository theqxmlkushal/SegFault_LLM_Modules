import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from modules.m3_itinerary_builder import ItineraryBuilder


class MockLLMClient:
    def __init__(self, response_json: str):
        self._response = response_json

    def chat_completion(self, messages, temperature=0.7, max_tokens=None, json_mode=False):
        # Simulate returning a JSON string
        return self._response

    def extract_json(self, text: str):
        import json
        return json.loads(text)

    def generate(self, system_prompt, user_prompt, conversation_history=None, temperature=None, max_tokens=None, json_mode=False):
        # For tests, generate returns the same JSON
        return self._response


def test_itinerary_builder_success():
    # Minimal valid itinerary JSON
    valid_json = '''{
        "destination": "Mulshi",
        "duration": 2,
        "days": [
            {"day": 1, "title": "Arrival and Relax", "schedule": [{"time": "09:00", "activity": "Ride around lake"}]},
            {"day": 2, "title": "Relax and Return", "schedule": [{"time": "10:00", "activity": "Short trek"}]}            
        ],
        "packing_list": ["Helmet","Water bottle"],
        "important_notes": ["Check weather"],
        "emergency_contacts": {"Local": "+91-1234567890"}
    }'''

    mock = MockLLMClient(valid_json)
    builder = ItineraryBuilder(llm_client=mock)

    # Create fake intent and destination minimal objects matching expected attributes
    class FakeIntent:
        duration_days = 2
        budget = "3000"
        group_size = 2
        interests = ["relax"]

    class FakeDest:
        name = "Mulshi"

    itinerary = builder.build(FakeIntent(), FakeDest())

    assert itinerary.destination == "Mulshi"
    assert itinerary.duration == 2
    assert len(itinerary.days) == 2
