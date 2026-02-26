# WanderAI Modules — Implementation & How It Works

This document explains the runtime flow, file roles, and where to change presentation/formatting.

Overview
- The project is a modular chatbot (M0..M6) with a central engine, simple RAG grounding, and validation layers to reduce hallucination.
- Key aims: keep module calls explicit, validate structured outputs, and present friendly user-facing responses.

Main components
- `modules/chatbot_core.py` (Engine V3): session-aware core, routing, module orchestration, verification, and post-processing. Uses `ModuleDispatcher` for task modules.
- `modules/chatbot_engine.py` (Engine V2): legacy engine used by the interactive shell; similar flow with module pipeline.
- `modules/module_dispatcher.py`: centralizes M0..M3 invocation and confirms intent before running modules.
- `modules/m0_query_refiner.py`: cleans and normalizes user queries.
- `modules/m1_intent_extractor.py`: extracts structured `TravelIntent` (with a regex fallback for destination extraction).
- `modules/m2_destination_suggester.py`: suggests destinations using SimpleRAG and LLM reasoning.
- `modules/m3_itinerary_builder.py`: builds an `Itinerary` Pydantic model from LLM JSON output; includes auto-reask for citations on validation failure.
- `utils/llm_client.py`: unified LLM client with `chat_completion()` and `generate()` wrappers.
- `utils/rag_engine.py`: simple keyword-based retrieval with source tracking.
- `response_validation.py`: multi-layer validators, a claims verifier, and strict RAG context generator.
- `utils/formatters.py`: new — formats structured outputs (itineraries) into emoji-rich, user-friendly text.
- `api_adapter.py`: minimal wrapper for backend developers to call `handle_message()`.

Data flow (per message)
1. Session created or retrieved.
2. Router classifies intent (RAG-only vs TASK_MODULES).
3. If TASK_MODULES: `ModuleDispatcher` runs M0 (refiner) → M1 (intent) → M2 (suggest) → M3 (itinerary) as needed.
   - `M3` attempts to parse LLM JSON into `Itinerary`. If parsing fails or `days` are empty, it auto-reasks the LLM requesting `sources` and retries.
4. All generated text is passed to `response_validation` which runs regex-based checks and `verify_claims_against_rag`.
   - Unsupported claims are conservatively redacted and the bot apologizes.
5. Post-processing: if response type is `itinerary`, `utils.formatters.beautify_itinerary()` is applied to produce `response_pretty` and a user-facing `response` string.

How presentation is controlled
- To change beautified output (emojis, headings, bullet styles), edit `utils/formatters.py`:
  - `beautify_itinerary(it: Dict[str, Any]) -> str` builds the pretty text. Modify emoji choices, Markdown vs plain text, or add HTML if you render in a web UI.
- To change tone/safety, edit prompts in `prompts.py` (system prompts used by modules) and `response_validation.py` rules.

How to add a new module
1. Create `modules/mX_module_name.py` implementing a small class with deterministic input/output (Pydantic models for structured outputs).
2. Register module instances in `chatbot_core.__init__` and use `ModuleDispatcher` to call them.
3. Add unit tests in `tests/` using `MockLLMClient` to ensure deterministic behavior.

Best practices to avoid hallucination
- Keep KB authoritative and current (use webhooks to push updates).
- Prefer structured outputs (JSON) from LLMs with `json_mode=True` and validate via Pydantic.
- Use low temperature for extraction modules (M0/M1) and slightly higher for creative text, but always validate.
- Replace `SimpleRAG` with embeddings+vector search for robust retrieval when KB grows.

Where to change formatting for web frontends
- `utils/formatters.py` can be adapted to return HTML or a small JSON representation for the frontend.
- `api_adapter.handle_message()` returns `response` (pretty string) and `data` (raw JSON) so the frontend can choose how to render.

If you want, I can:
- Add HTML/Markdown-to-HTML rendering helper and example web UI.
- Implement vector RAG for better grounding.
- Convert `utils/formatters.beautify_itinerary` to return both Markdown and an HTML-safe version.
