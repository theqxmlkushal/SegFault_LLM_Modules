from response_validation import ResponseValidationLayer


class FakeRAG:
    def retrieve_with_sources(self, query, top_k=3):
        # Return docs only for known items
        known = {
            "Lonavala": {"documents": [{"text": "Lonavala is 64 km from Pune."}], "sources": ["places.json"]},
            "Tiger's Leap": {"documents": [{"text": "Tiger's Leap is a viewpoint near Lonavala."}], "sources": ["places.json"]}
        }
        return known.get(query, {"documents": [], "sources": []})


def test_verify_and_redact_supported_and_unsupported():
    validator = ResponseValidationLayer()
    rag = FakeRAG()

    # A response containing one supported claim and one unsupported
    response = "Lonavala is 64 km from Pune. The new Skybridge at Lonavala has 10 glass panels."

    result = validator.verify_and_redact(response, rag)

    assert result["verified"] is False
    assert "Unverified" in result["redacted"]
    assert "Lonavala is 64 km from Pune" in result["redacted"] or "Lonavala" in result["redacted"]