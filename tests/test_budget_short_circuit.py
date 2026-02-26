import types

from modules.module_dispatcher import ModuleDispatcher
from modules.m0_query_refiner import QueryRefiner


class DummyLLMClient:
    def __init__(self, reply):
        self.reply = reply

    def chat_completion(self, *args, **kwargs):
        return self.reply


class FakeSession:
    def __init__(self):
        self.session_id = "test-session"
        self.message_history = []


class FakeRoutingDecision:
    def __init__(self):
        self.intent_type = types.SimpleNamespace(name="TRIP_SUGGESTION")
        self.confidence = 0.9


class FakeEngine:
    def __init__(self, refiner):
        self.query_refiner = refiner

    def _handle_fallback(self, session, routing_decision):
        return {"response": "fallback", "has_answer": False}


def test_budget_short_circuit():
    # Arrange: mock refiner to return a CRITICAL BUDGET flag
    critical_refined = "3-day trip to Lonavala for 1 person. Budget: 250 INR. [CRITICAL BUDGET CONSTRAINT: Impossible budget for duration]"
    llm = DummyLLMClient(critical_refined)
    refiner = QueryRefiner(llm_client=llm)

    engine = FakeEngine(refiner)
    dispatcher = ModuleDispatcher(engine)
    session = FakeSession()
    routing = FakeRoutingDecision()

    # Act
    result = dispatcher.dispatch("Plan a trip to Lonavala for 3 days 2 nights with 250 rupees", session, routing)

    # Assert
    assert isinstance(result, dict)
    assert result.get("validation_status") == "rejected_budget"
    assert result.get("data", {}).get("reason") == "critical_budget"
