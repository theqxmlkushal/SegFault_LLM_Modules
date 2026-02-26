from modules.chatbot_core import WanderAIChatbotCoreV3
from datetime import datetime


class DummyLLM:
    def __init__(self, reply_text):
        self.reply_text = reply_text

    def chat_completion(self, *args, **kwargs):
        # Return a generated response that contains a supported and unsupported claim
        return self.reply_text
    def generate(self, *args, **kwargs):
        # For calls that use the unified generate() helper, return the same reply
        return self.reply_text

    def extract_json(self, text: str):
        # Not used in this test but provide a safe passthrough
        return {}


class FakeRAGEngine:
    def __init__(self):
        # Provide a knowledge_base_timestamp attribute expected by the core
        self.knowledge_base_timestamp = datetime.now()

    def retrieve_with_sources(self, query, top_k=3):
        if "Lonavala" in query:
            return {"documents": [{"text": "Lonavala is 64 km from Pune."}], "sources": ["places.json"], "facts": [{"fact": "Lonavala is 64 km from Pune"}]}
        return {"documents": [], "sources": [], "facts": []}

    def conditional_refresh(self):
        return False


def test_chat_flow_redaction():
    # Construct a dummy LLM response containing an unsupported made-up claim
    llm_reply = (
        "Lonavala is 64 km from Pune. The Hidden Palace of Lonavala has marble halls and was built in 1880."
    )

    core = WanderAIChatbotCoreV3(rag_engine=FakeRAGEngine(), llm_client=DummyLLM(llm_reply))

    result = core.process_message("Tell me about Lonavala", session_id=None, refresh_kb=False)

    # Expect redaction of unsupported claim and partial validation status
    assert result.get("validation_status") in ("partial", "grounded")
    assert "Unverified" in result.get("response") or "couldn't verify" in result.get("response").lower()
