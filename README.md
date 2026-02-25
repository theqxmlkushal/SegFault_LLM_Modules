# WanderAI: Core LLM Journey Engine

WanderAI is a high-performance, modular collection of LLM-powered agents designed to build intelligent travel planning pipelines. This repository focuses on the stable **M1-M3 Agent Core**, delivering a seamless flow from natural language intent to detailed, actionable itineraries.

## 🚀 Key Features

- **Agent-Grade Robustness**: Every module features ultra-robust Pydantic models with aggressive structural repair and key mapping.
- **Universal JSON Recovery**: The `LLMClient` salvaged valid data from messy LLM outputs through deep structural normalization.
- **Unified LLM Intelligence**: Built-in support for Groq (Llama 3) and Gemini with automatic fallback logic.
- **RAG-Powered Personalization**: Keyword-based Retrieval-Augmented Generation for locally grounded destination suggestions.
- **Conversational Engine**: A state-aware chatbot controller that handles follow-ups, context, and flexible travel queries.
- **Backend Ready**: Includes a dedicated integration guide and reusable engine for seamless API development.
- **Production-Ready Demo**: High-polish terminal interfaces (`run.py` and `chatbot.py`) to experience the full agentic flow.

## 🛠️ Project Structure

```text
├── modules/               # Core LLM Agent Modules
│   ├── m1_intent_extractor.py     # Parses raw queries into structured intents
│   ├── m2_destination_suggester.py # RAG-based personalized recommendations
│   └── m3_itinerary_builder.py    # Generates detailed day-by-day plans
├── utils/                 # Utilities
│   ├── llm_client.py      # Unified API wrapper with deep repair
│   └── rag_engine.py      # Keyword-based RAG engine
├── knowledge_base/        # RAG Data (JSON)
├── config.py              # Environment configuration
├── run.py                 # Linear Pipeline Demo
├── chatbot.py             # Conversational Chatbot Demo
├── api_example.py         # Backend Integration Example
├── BACKEND_INTEGRATION.md # Developer Guide for Backend Integration
├── requirements.txt       # Project dependencies
└── .env                   # API Keys (Git ignored)
```

## 🚥 Quick Start

### 1. Setup Environment
```bash
pip install -r requirements.txt
```

### 2. Configure API Keys
Create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here
PRIMARY_LLM=groq
```

### 3. Experience the Flow
- **Linear Pipeline**: `python run.py` (M1 -> M2 -> M3)
- **Conversational Chatbot**: `python chatbot.py` (End-to-end with history and context)

## 🛠️ Backend Integration
If you are integrating these modules into a web backend (FastAPI, Node.js, etc.), please refer to **[BACKEND_INTEGRATION.md](file:///d:/AMD_Hackathon/wanderai_llm_modules/BACKEND_INTEGRATION.md)** for architecture recommendations and code examples.

## 🤖 Core Pipeline

1.  **M1: Intent Extractor**: Converts messy user queries into clean data (budget, duration, group size, interests).
2.  **M2: Destination Suggester**: Matches intent against the local knowledge base to suggest the best locations.
3.  **M3: Itinerary Builder**: Generates specific timings, activities, and cost estimates for each day of the trip.

## 🔧 Integration & Extensibility

The system is designed to be modular. You can swap out the RAG engine, add specialized ML prediction modules (for crowd or experience scores), or plug the modules into a FastAPI/Express backend.

## 📄 License

MIT License - Free for experimental and commercial use.
