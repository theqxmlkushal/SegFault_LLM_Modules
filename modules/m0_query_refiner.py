"""
M0: Query Refiner Module
Pre-processes raw user queries into clean, structured prompts for the pipeline
"""
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any

sys.path.append(str(Path(__file__).parent.parent))

from utils.llm_client import LLMClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QueryRefiner:
    """
    M0: Query Refiner
    Normalizes complex user queries into a clean travel request
    """
    
    SYSTEM_PROMPT = """You are WanderAI's query normalization expert.
Your job is to take a conversational user travel query and turn it into a clean, concise, and structured travel request.

Contextual Rules:
1. Use the provided "Conversation History" to resolve pronouns (e.g., "it", "there") and follow-ups (e.g., "any other?").
2. If the user asks for "other" or "another", specifically mention "search for NEW alternatives" in the refined query.
3. If the user confirms a place (e.g., "let's go", "looks good"), the refined query should start with "CONFIRMED: [Place Name]".
4. Extract only the core travel intent (destination, budget, people, interests, duration).
5. Remove conversational filler (e.g., "so like", "i am thinking").
6. Ensure numerical values are clear (e.g., "1.5k" -> "1500").
7. Output ONLY the refined query string.

Example 1 (Follow-up):
History: Bot suggested Alibaug.
Input: "any other beach?"
Output: "Search for NEW beach alternatives other than Alibaug."

Example 2 (Confirmation):
History: Bot suggested Karla Caves.
Input: "looks good, plan it"
Output: "CONFIRMED: Karla Caves. Proceed to build itinerary."
"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def refine(self, raw_query: str, history: str = "") -> str:
        """Refine a raw user query into a clean prompt using optional history"""
        logger.info(f"Refining query: {raw_query}")
        
        prompt = f"Conversation History:\n{history}\n\nRefine this query: {raw_query}" if history else f"Refine this query: {raw_query}"
        
        response = self.llm_client.chat_completion(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            json_mode=False
        )
        
        refined_query = response.strip()
        logger.info(f"Refined query: {refined_query}")
        return refined_query

if __name__ == "__main__":
    refiner = QueryRefiner()
    test_query = "Plan a pune vist to dagdusheth for a single day in pune so like i have a budget of 1.5k for 2 people with suggestion of great aesthetic cafes after dagdusheth visit"
    print(f"Original: {test_query}")
    print(f"Refined: {refiner.refine(test_query)}")
