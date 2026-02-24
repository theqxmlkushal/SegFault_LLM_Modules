"""
Unified LLM Client for Groq and Gemini APIs
Provides a simple interface with automatic fallback
"""
import json
from typing import Optional, Dict, Any, List
from enum import Enum
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    print("Warning: Groq SDK not installed. Install with: pip install groq")

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: Gemini SDK not installed. Install with: pip install google-generativeai")

from config import settings


class LLMProvider(str, Enum):
    GROQ = "groq"
    GEMINI = "gemini"


class LLMClient:
    """Unified client for multiple LLM providers with automatic fallback"""
    
    def __init__(
        self,
        primary_provider: Optional[LLMProvider] = None,
        groq_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None
    ):
        self.primary_provider = primary_provider or LLMProvider(settings.PRIMARY_LLM)
        
        # Initialize Groq
        self.groq_client = None
        if GROQ_AVAILABLE and (groq_api_key or settings.GROQ_API_KEY):
            try:
                self.groq_client = Groq(api_key=groq_api_key or settings.GROQ_API_KEY)
            except Exception as e:
                print(f"Failed to initialize Groq client: {e}")
        
        # Initialize Gemini
        self.gemini_client = None
        if GEMINI_AVAILABLE and (gemini_api_key or settings.GEMINI_API_KEY):
            try:
                genai.configure(api_key=gemini_api_key or settings.GEMINI_API_KEY)
                self.gemini_client = genai.GenerativeModel(settings.GEMINI_MODEL)
            except Exception as e:
                print(f"Failed to initialize Gemini client: {e}")
        
        # Validate at least one client is available
        if not self.groq_client and not self.gemini_client:
            raise ValueError("No LLM client available. Please configure API keys.")
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        provider: Optional[LLMProvider] = None
    ) -> str:
        """
        Send chat completion request with automatic fallback
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            json_mode: Force JSON output format
            provider: Override primary provider
        
        Returns:
            Generated text response
        """
        provider = provider or self.primary_provider
        
        # Try primary provider
        try:
            if provider == LLMProvider.GROQ and self.groq_client:
                return self._groq_completion(messages, temperature, max_tokens, json_mode)
            elif provider == LLMProvider.GEMINI and self.gemini_client:
                return self._gemini_completion(messages, temperature, max_tokens, json_mode)
        except Exception as e:
            print(f"Primary provider {provider} failed: {e}. Trying fallback...")
        
        # Try fallback provider
        try:
            if provider == LLMProvider.GROQ and self.gemini_client:
                return self._gemini_completion(messages, temperature, max_tokens, json_mode)
            elif provider == LLMProvider.GEMINI and self.groq_client:
                return self._groq_completion(messages, temperature, max_tokens, json_mode)
        except Exception as e:
            raise Exception(f"All LLM providers failed. Last error: {e}")
    
    def _groq_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        json_mode: bool
    ) -> str:
        """Groq-specific completion"""
        kwargs = {
            "model": settings.GROQ_MODEL,
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
            # Ensure system message requests JSON
            if messages[0]["role"] == "system":
                messages[0]["content"] += "\n\nRespond with valid JSON only."
        
        response = self.groq_client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    
    def _gemini_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        json_mode: bool
    ) -> str:
        """Gemini-specific completion"""
        # Convert messages to Gemini format
        prompt_parts = []
        for msg in messages:
            role_prefix = f"[{msg['role'].upper()}]: " if msg['role'] != 'user' else ""
            prompt_parts.append(f"{role_prefix}{msg['content']}")
        
        prompt = "\n\n".join(prompt_parts)
        
        if json_mode:
            prompt += "\n\nRespond with valid JSON only."
        
        generation_config = {
            "temperature": temperature,
        }
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens
        
        response = self.gemini_client.generate_content(
            prompt,
            generation_config=generation_config
        )
        
        return response.text
    
    def extract_json(self, text: str) -> Dict[str, Any]:
        """
        Extract JSON from LLM response with deep repair and structural normalization.
        Handles markdown blocks, prefix text, and nested structures.
        """
        text = text.strip()
        
        # 1. Try to find the widest JSON-like block {} or []
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        
        if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
            # Fallback for list responses if it's M2 or similar
            start_idx = text.find('[')
            end_idx = text.rfind(']')
            
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_text = text[start_idx:end_idx + 1]
        else:
            json_text = text

        try:
            data = json.loads(json_text)
            return self.repair_json_structure(data)
        except json.JSONDecodeError as e:
            # Last ditch cleaning: remove markdown blocks and common noise
            clean_text = re.sub(r'```json\s*|\s*```', '', text).strip()
            # Try to grab just the braces again from clean text
            s2 = clean_text.find('{')
            e2 = clean_text.rfind('}')
            if s2 != -1 and e2 != -1 and e2 > s2:
                try:
                    return self.repair_json_structure(json.loads(clean_text[s2:e2+1]))
                except: pass
                
            raise ValueError(f"Failed to parse JSON from LLM response: {e}")

    def repair_json_structure(self, data: Any) -> Any:
        """
        Recursively find and normalize the core payload in a potentially nested dict.
        """
        if not isinstance(data, dict):
            return data

        # Common keys used by LLMs to wrap responses
        structural_keys = ["itinerary", "travel_intent", "intent", "destination_suggestions", "data", "results", "response", "content"]
        
        # If we find a primary structural key, and it wraps another dict/list
        for key in structural_keys:
            if key in data and isinstance(data[key], (dict, list)):
                # If it's the core payload, unwrap it but merge non-overlapping root keys
                payload = data[key]
                if isinstance(payload, dict):
                    for k, v in data.items():
                        if k != key and k not in payload:
                            payload[k] = v
                    return payload
                else: 
                    # If it's a list (e.g. destinations), we can't easily merge 
                    # unless we wrap it, so we just return the list
                    return payload
        
        # Handle single-key dictionaries
        if len(data) == 1:
            key = list(data.keys())[0]
            if isinstance(data[key], (dict, list)):
                return data[key]
        
        return data


# Convenience function for quick usage
def quick_chat(
    prompt: str,
    system_message: Optional[str] = None,
    temperature: float = 0.7,
    json_mode: bool = False
) -> str:
    """
    Quick chat completion without managing client instance
    
    Args:
        prompt: User prompt
        system_message: Optional system message
        temperature: Sampling temperature
        json_mode: Force JSON output
    
    Returns:
        Generated response
    """
    client = LLMClient()
    
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})
    
    return client.chat_completion(messages, temperature=temperature, json_mode=json_mode)


# Example usage
if __name__ == "__main__":
    # Test the client
    client = LLMClient()
    
    response = client.chat_completion(
        messages=[
            {"role": "system", "content": "You are a helpful travel assistant."},
            {"role": "user", "content": "Suggest a weekend trip near Pune for beach lovers."}
        ],
        temperature=0.7
    )
    
    print("Response:", response)
    
    # Test JSON mode
    json_response = client.chat_completion(
        messages=[
            {"role": "system", "content": "Extract travel intent from user message."},
            {"role": "user", "content": "I want to visit a beach this weekend with 3 friends, budget 5000 rupees"}
        ],
        json_mode=True
    )
    
    print("\nJSON Response:", json_response)
    parsed = client.extract_json(json_response)
    print("Parsed:", parsed)
