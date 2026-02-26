# WanderAI: Core LLM Journey Engine

WanderAI is a modular LLM-based travel planning engine that converts natural-language requests into validated, actionable itineraries. The codebase emphasizes conservative generation, grounding with a local knowledge base (RAG), structured outputs (Pydantic models), and easy backend integration.

## Highlights

- Module pipeline (M0..M3) with a `ModuleDispatcher` to run specialized modules only when needed.
- Unified LLM client (`utils/llm_client.py`) offering `generate()` and recovery tools to parse messy LLM outputs.
- Response validation layer (`response_validation.py`) that cross-checks claims against the local RAG and redacts unsupported assertions.
- Auto-reask pattern in the `ItineraryBuilder` to request citations and retry when JSON validation fails.
- Lightweight integration surface (`api_adapter.py`) and developer docs for backend teams.

## Repository Layout (important files)

```
wanderai_llm_modules/
├── modules/
│   ├── module_dispatcher.py
│   ├── m0_query_refiner.py
│   ├── m1_intent_extractor.py
│   ├── m2_destination_suggester.py
│   └── m3_itinerary_builder.py
├── utils/
│   ├── llm_client.py
│   ├── rag_engine.py
│   └── formatters.py        # prettify outputs (emoji/markdown)
├── knowledge_base/          # JSON docs used by SimpleRAG
├── response_validation.py   # verifier and conservative redaction
├── api_adapter.py           # backend-friendly handle_message() wrapper
├── run.py                   # pipeline demo
├── chatbot.py               # conversational demo
├── tests/                   # unit tests (MockLLMClient)
├── DOCUMENTATION.md         # architecture notes and how-to
└── README.md
```

## Quick Start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Add your LLM API keys to `.env` (root):

```ini
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here
PRIMARY_LLM=groq
```

3. Run demos:

```bash
python run.py       # linear M1->M2->M3 pipeline demo
python chatbot.py   # conversational demo with session context
```

## Tests

Unit tests use a `MockLLMClient` so they run offline. Execute:

```bash
pytest -q
```

## Backend Integration

Use `api_adapter.handle_message()` as the primary entrypoint for servers. It returns a dict with `response` (pretty string) and `data` (raw structured JSON). See `DOCUMENTATION.md` and `BACKEND_INTEGRATION.md` for examples and recommended patterns.

## Notes & Next Steps

- Current RAG: keyword-based (`knowledge_base/*.json`). For production grounding, we recommend migrating to embeddings + vector search (FAISS/Chroma/Pinecone).
- The code supports both Groq and Gemini; set `PRIMARY_LLM` in `.env`.
- Pydantic v2 migration warnings may appear; the code includes compatibility helpers but a full migration is planned.

If you'd like, I can:

- Add an example FastAPI wrapper that calls `api_adapter.handle_message()` and returns JSON to clients.
- Implement vector RAG indexing and a migration script.

---
MIT License
