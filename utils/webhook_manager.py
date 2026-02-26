"""
Webhook Manager for Knowledge Base Updates
Handles incoming webhook notifications to update the RAG knowledge base dynamically
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import json
import logging
import hashlib
import hmac
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path
from utils.rag_engine import SimpleRAG

logger = logging.getLogger(__name__)


class WebhookValidator:
    """
    Validate webhook payloads with signature verification
    """

    def __init__(self, webhook_secret: Optional[str] = None):
        self.webhook_secret = webhook_secret

    def verify_signature(self, payload: str, signature: str) -> bool:
        """
        Verify webhook signature using HMAC-SHA256

        Args:
            payload: Raw webhook payload
           signature: Signature from webhook header (X-Webhook-Signature)

        Returns:
            True if signature is valid
        """
        if not self.webhook_secret:
            return True  # No secret configured, skip validation

        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        # Timing-safe comparison
        return hmac.compare_digest(expected_signature, signature)

    def validate_payload(self, data: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate webhook payload structure

        Args:
            data: Webhook payload

        Returns:
            (is_valid, error_message)
        """
        # Check required fields
        if "action" not in data:
            return False, "Missing 'action' field"

        action = data.get("action", "").lower()
        if action not in ["add", "update", "delete"]:
            return False, f"Invalid action: {action}"

        if "type" not in data:
            return False, "Missing 'type' field"

        type_val = data.get("type", "").lower()
        if type_val not in ["place", "tip", "category"]:
            return False, f"Invalid type: {type_val}"

        if "data" not in data or not isinstance(data["data"], dict):
            return False, "Missing 'data' field or not a dictionary"

        # Validate data has at least name/id for identification
        data_obj = data["data"]
        if "name" not in data_obj and "id" not in data_obj:
            return False, "Data must have 'name' or 'id' field"

        return True, ""


class WebhookManager:
    """
    Manages webhook updates for the RAG knowledge base
    """

    def __init__(self, rag_engine: SimpleRAG, webhook_secret: Optional[str] = None,
                 updates_log_path: Optional[str] = None):
        self.rag = rag_engine
        self.validator = WebhookValidator(webhook_secret)
        self.updates_log_path = Path(updates_log_path or "knowledge_base/updates_log.json")
        self.updates_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_updates_log()

    def _load_updates_log(self):
        """Load existing updates log"""
        if self.updates_log_path.exists():
            try:
                with open(self.updates_log_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "updates" in data:
                        self.updates = data["updates"]
                    else:
                        self.updates = data if isinstance(data, list) else []
                logger.info(f"Loaded {len(self.updates)} updates from log")
            except Exception as e:
                logger.error(f"Error loading updates log: {e}")
                self.updates = []
        else:
            self.updates = []

    def _save_updates_log(self):
        """Persist updates log to disk"""
        try:
            with open(self.updates_log_path, 'w', encoding='utf-8') as f:
                json.dump({"updates": self.updates, "count": len(self.updates)}, f, indent=2)
            logger.info(f"Saved {len(self.updates)} updates to log")
        except Exception as e:
            logger.error(f"Error saving updates log: {e}")

    def process_webhook(self,
                       payload: Dict[str, Any],
                       signature: Optional[str] = None) -> tuple[bool, str]:
        """
        Process incoming webhook

        Args:
            payload: Webhook payload
            signature: Optional signature for verification

        Returns:
            (success, message)
        """
        # Validate signature if provided
        if signature:
            payload_str = json.dumps(payload, sort_keys=True)
            if not self.validator.verify_signature(payload_str, signature):
                logger.warning("Invalid webhook signature")
                return False, "Invalid signature"

        # Validate payload structure
        is_valid, error_msg = self.validator.validate_payload(payload)
        if not is_valid:
            logger.warning(f"Invalid payload: {error_msg}")
            return False, error_msg

        # Process the update
        try:
            action = payload.get("action", "").lower()
            data = payload.get("data", {})
            update_type = payload.get("type", "").lower()

            # Add timestamp if not present
            if "timestamp" not in payload:
                payload["timestamp"] = datetime.now().isoformat()

            # Log the update
            self.updates.append(payload)
            self._save_updates_log()

            # Apply to RAG engine
            self.rag.add_update(payload)

            logger.info(f"Processed webhook: {action} {update_type} - {data.get('name', 'unknown')}")
            return True, f"Successfully processed {action} for {data.get('name', 'unknown')}"

        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            return False, f"Error: {str(e)}"

    def get_recent_updates(self, hours: int = 24) -> list[Dict[str, Any]]:
        """Get recent updates within X hours"""
        if not self.updates:
            return []

        now = datetime.now()
        recent = []

        for update in self.updates:
            try:
                timestamp_str = update.get("timestamp", "")
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    hours_ago = (now - timestamp).total_seconds() / 3600
                    if hours_ago <= hours:
                        recent.append(update)
            except Exception:
                pass

        return recent

    def clear_old_updates(self, hours: int = 24 * 7):
        """Clear updates older than X hours (default 7 days) to keep log clean"""
        if not self.updates:
            return

        now = datetime.now()
        recent_updates = []

        for update in self.updates:
            try:
                timestamp_str = update.get("timestamp", "")
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    hours_ago = (now - timestamp).total_seconds() / 3600
                    if hours_ago <= hours:
                        recent_updates.append(update)
            except Exception:
                recent_updates.append(update)  # Keep if parse fails

        old_count = len(self.updates)
        self.updates = recent_updates
        self._save_updates_log()

        if old_count > len(self.updates):
            logger.info(f"Cleaned {old_count - len(self.updates)} old updates from log")

    def get_stats(self) -> Dict[str, Any]:
        """Get webhook statistics"""
        return {
            "total_updates": len(self.updates),
            "recent_updates_24h": len(self.get_recent_updates(24)),
            "updates_by_action": {
                "add": len([u for u in self.updates if u.get("action") == "add"]),
                "update": len([u for u in self.updates if u.get("action") == "update"]),
                "delete": len([u for u in self.updates if u.get("action") == "delete"])
            },
            "kb_last_updated": self.rag.knowledge_base_timestamp.isoformat() if self.rag else None
        }


if __name__ == "__main__":
    # Test webhook manager
    rag = SimpleRAG()
    manager = WebhookManager(rag, webhook_secret="test-secret")

    # Example webhook payloads
    test_payloads = [
        {
            "action": "add",
            "type": "place",
            "data": {
                "name": "New Beach Spot",
                "category": "beach",
                "cost": "₹500",
                "description": "A hidden gem beach"
            }
        },
        {
            "action": "update",
            "type": "place",
            "data": {
                "name": "Alibaug Beach",
                "cost": "₹800"  # Updated cost
            }
        }
    ]

    print("=== Webhook Manager Test ===\n")
    for payload in test_payloads:
        success, msg = manager.process_webhook(payload)
        print(f"Result: {success} - {msg}\n")

    print("\nStats:")
    print(json.dumps(manager.get_stats(), indent=2))
