"""
M6: Place Description Generator Module
Generates engaging, RAG-grounded descriptions for places
"""
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any

sys.path.append(str(Path(__file__).parent.parent))

from utils.llm_client import LLMClient
from utils.rag_engine import SimpleRAG
from utils.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PlaceDescriptionGenerator:
    """
    M6: Place Description Generator
    Short, engaging descriptions for place detail pages grounded in RAG
    """
    
    SYSTEM_PROMPT = """You are WanderAI's travel writer.
Your job is to create short, factual, and descriptive snippets for specific travel destinations.

Rules:
1. STRICT FACTUAL GROUNDING: Use ONLY the provided context. DO NOT hallucinate facts, features, or distances.
2. The description should be 3-5 sentences long.
3. Tone: Maintain a balanced, informative, and professional tone. Avoid overly flowery or promotional language if the context is thin.
4. Highlights: Mention unique features or tips ONLY if they appear in the provided context.
5. If the context is missing, output: "This place is in our database but detailed descriptions are currently being updated. It is located [Distance] from Pune." (Fill in distance from context).
"""

    def __init__(self, llm_client: Optional[LLMClient] = None, rag_engine: Optional[SimpleRAG] = None):
        self.llm_client = llm_client or LLMClient()
        self.rag_engine = rag_engine or SimpleRAG()
    
    def generate(self, place_name: str) -> str:
        """Generate a grounded description for a place"""
        logger.info(f"Generating description for: {place_name}")
        
        # 1. Retrieve context from RAG
        context = self.rag_engine.search(place_name, top_k=2)

        # If no grounded docs are available, refuse to hallucinate and return safe message
        if not context or "No relevant documents found" in str(context):
            logger.warning(f"No specific RAG data found for {place_name}. Refusing to hallucinate.")
            return (
                f"{place_name} exists in our knowledge base, but detailed descriptions are currently unavailable. "
                "Please provide more context or ask for nearby alternatives."
            )

        # 2. Generate description using conservative module temperature
        prompt = f"""
Place: {place_name}
Context: {context}

Generate a short, engaging description for this place.
"""
        response = self.llm_client.chat_completion(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=getattr(settings, 'MODULE_TEMPERATURE', 0.0),
            json_mode=False
        )

        description = response.strip()
        logger.info(f"Description generated successfully for {place_name}")
        return description

if __name__ == "__main__":
    generator = PlaceDescriptionGenerator()
    
    # Test with a known place
    place = "Dagdusheth Halwai Ganapati Temple"
    print(f"--- Description for {place} ---")
    print(generator.generate(place))
    print("\n")
    
    # Test with another place
    place = "Karla Caves"
    print(f"--- Description for {place} ---")
    print(generator.generate(place))
