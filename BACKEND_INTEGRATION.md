# 🛠️ WanderAI: Backend Integration Guide

This guide is for the developer responsible for integrating the WanderAI Journey Engine into the backend (FastAPI, Express, Node.js, etc.).

## 📋 Important Files
To get the chatbot running, you need the following files from this repository:

| Content | Paths | Description |
| :--- | :--- | :--- |
| **Core Modules** | `modules/m0...m6.py` | The actual LLM logic and agents. |
| **Engine** | `modules/chatbot_engine.py` | The main class that coordinates the conversational flow. |
| **Utilities** | `utils/` | LLM client (Groq/Gemini) and RAG engine. |
| **Data** | `knowledge_base/` | JSON files containing the destination data. |
| **Config** | `config.py`, `.env` | Environment variables and API keys. |

## 🏗️ Recommended API Architecture

The system is designed to be **stateless**. The backend should maintain the session state (conversation history) and pass it to the `WanderAIChatbot` for each request.

### 1. Chat Endpoint (`POST /api/chat`)
**Request Body:**
```json
{
  "user_id": "12345",
  "message": "any other beach?",
  "history": [
    {"role": "User", "content": "I want to go to a beach."},
    {"role": "Bot", "content": "Based on our chat, I suggest Alibaug Beach! ..."}
  ]
}
```

**Implementation Example (Pseudocode):**
```python
from modules.chatbot_engine import WanderAIChatbot

bot = WanderAIChatbot()

@app.post("/chat")
def handle_chat(request):
    # Pass history so the LLM understands context
    response = bot.process_message(request.message, request.history)
    return response
```

## 🧠 State Management Tips
- **History Tracking**: The `history` list is crucial for M0 (Query Refiner) to resolve context like "any other?".
- **Suggested Places**: For the best UX, keep a list of `suggested_places` in the user's session so the bot doesn't repeat itself when the user says "show me more".

## 🚀 Environment Setup
Ensure the backend server has the `requirements.txt` installed and the `.env` file contains valid keys for `GROQ_API_KEY` and `GEMINI_API_KEY`.
