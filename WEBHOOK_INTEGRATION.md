# Webhook Integration Guide

This document describes how to connect an external webhook to the WanderAI knowledge base so the chatbot sees the latest information.

Key ideas
- The repository stores a simple on-disk knowledge base under `knowledge_base/` (JSON files).
- A webhook endpoint (external) should POST updates (new or updated documents) to your backend.
- Your backend validates the webhook signature, writes the update into `knowledge_base/`, then calls the repo's `WebhookManager` to enqueue or apply the update.

Minimal integration steps for backend developers

1. Expose an HTTP endpoint in your backend (Flask/FastAPI/Express) that accepts webhook POSTs.

2. Validate signature and payload
- Use a shared secret (set `WEBHOOK_SECRET` in `.env`) to validate the payload signature.
- The repo contains `utils/webhook_manager.py` with helper functions — call `WebhookManager.process_webhook(payload, signature)` to validate and get canonical update structure.

3. Apply the update to the knowledge base
- After validation, write the new/updated document to `wanderai_llm_modules/knowledge_base/` (e.g., `places.json`).
- Keep writes atomic: write to a temp file then rename.

4. Notify the bot code (reload / enqueue)
- If your backend hosts the chatbot, call the project's `WebhookEventQueue.enqueue(update)` (or `WebhookManager.apply_update(update)`) to ensure KB is refreshed.
- If the bot runs in a separate process, consider calling a lightweight `/admin/reload-kb` endpoint on the bot process or use a shared message queue (Redis, SQS).

5. Best practices
- Send minimal diffs (only changed documents) to reduce load.
- Include a `source` field and `timestamp` with each update.
- Rate-limit webhook processing and batch small updates.

Example FastAPI handler (pseudo-code)
```python
from fastapi import FastAPI, Request, Header
from utils.webhook_manager import WebhookManager

app = FastAPI()
wm = WebhookManager()

@app.post("/webhook")
async def webhook(request: Request, x_signature: str = Header(None)):
    payload = await request.json()
    # validate and normalize
    ok, update = wm.process_webhook(payload, x_signature)
    if not ok:
        return {"status": "invalid"}

    # write to knowledge base file atomically
    # e.g., open('knowledge_base/places.json.tmp','w') -> rename

    # enqueue for processing
    wm.apply_update(update)

    return {"status": "accepted"}
```

Notes
- The repo's `WebhookManager` and `WebhookEventQueue` are intentionally simple and can be swapped for a real queue (Redis/DB) in production.
- Keep webhook secret rotation and replay protection in mind.

If you want, I can provide a drop-in FastAPI example in this repo wired to the existing `WebhookManager` and a small integration test.
