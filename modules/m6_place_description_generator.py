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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PlaceDescriptionGenerator:
    """
    M6: Place Description Generator
    Short, engaging descriptions for place detail pages grounded in RAG
    """
    
    SYSTEM_PROMPT = """You are WanderAI's travel writer.
Your job is to create short, engaging, and highly descriptive snippets for specific travel destinations.

Rules:
1. Use the provided context to ensure accuracy. DO NOT hallucinate facts.
2. The description should be 3-5 sentences long.
3. Use an inviting, professional, and evocative tone.
4. Highlight unique features, best time to visit, or interesting tips mentioned in the context.
5. If the context is missing specific details, focus on what is known rather than making things up.
"""

    def __init__(self, llm_client: Optional[LLMClient] = None, rag_engine: Optional[SimpleRAG] = None):
        self.llm_client = llm_client or LLMClient()
        self.rag_engine = rag_engine or SimpleRAG()
    
    def generate(self, place_name: str) -> str:
        """Generate a grounded description for a place"""
        logger.info(f"Generating description for: {place_name}")
        
        # 1. Retrieve context from RAG
        context = self.rag_engine.search(place_name, top_k=2)
        
        if "No relevant documents found" in context:
            logger.warning(f"No specific RAG data found for {place_name}. Proceeding with general knowledge (caution).")
        
        # 2. Generate description
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
            temperature=0.7,
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
