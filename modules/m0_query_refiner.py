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
1. CONTEXTUAL CONTINUITY: Only use history to resolve pronouns ("it", "there") or follow-ups ("other", "better", "adjust X").
2. TOPIC SHIFT: If the user names a NEW destination or starts a fresh "Plan a trip" request without referencing the previous one, TREAT IT AS A NEW TRIP. DO NOT carry over specific constraints (like budget) from the previous failed trip unless explicitly asked.
3. PARAMETER ADJUSTMENTS: If the user says "adjust budget to X" or "make it 2 days", carry over the previous destination but update that specific parameter.
4. If the user confirms a place (e.g., "let's go", "looks good"), the refined query should start with "CONFIRMED: [Place Name]".
5. Reality Check: If the budget seems impossible for the duration (e.g., ₹250 for 3 days), append "[CRITICAL BUDGET CONSTRAINT: Impossible budget for duration]" to the output.
6. Extract only the core travel intent. Remove conversational filler.
7. Output ONLY the refined query string.

Example 1 (Follow-up):
History: Bot suggested Alibaug.
Input: "any other beach?"
Output: "Search for NEW beach alternatives other than Alibaug."

Example 2 (Impossible Budget):
Input: "3 day trip to Lonavala for 250 rupees"
Output: "3-day trip to Lonavala for 1 person. Budget: 250 INR. [CRITICAL BUDGET CONSTRAINT: Impossible budget for duration]"
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

    def refine_structured(self, raw_query: str, history: str = "") -> dict:
        """Return a structured result with flags for easier programmatic handling.

        Keeps `refine()` semantics for backward compatibility but provides a
        parsed dict containing `refined` and optional `flags` like
        `critical_budget`.
        """
        refined = self.refine(raw_query, history)
        flags = {}
        if isinstance(refined, str) and "[CRITICAL BUDGET CONSTRAINT" in refined:
            flags["critical_budget"] = True
        return {"refined": refined, "flags": flags}

if __name__ == "__main__":
    refiner = QueryRefiner()
    test_query = "Plan a pune vist to dagdusheth for a single day in pune so like i have a budget of 1.5k for 2 people with suggestion of great aesthetic cafes after dagdusheth visit"
    print(f"Original: {test_query}")
    print(f"Refined: {refiner.refine(test_query)}")
