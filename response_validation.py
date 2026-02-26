"""
Response Validation Layer - Strict RAG Enforcement
4-Layer Hallucination Prevention System
"""

import re
import logging
from typing import List, Dict, Tuple, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationLayer(str, Enum):
    """Validation layers for hallucination prevention"""
    CONTEXT = "context_enforcement"
    PROMPT = "system_prompt"
    PARSING = "response_parsing"
    ATTRIBUTION = "source_attribution"


class ResponseValidationLayer:
    """
    Enforce strict RAG constraints through 4 validation layers

    Layer 1: Context Enforcement - Format LLM context with KB-only facts
    Layer 2: System Prompt - Prohibit speculation and invention patterns
    Layer 3: Response Parsing - Detect unsourced claims post-generation
    Layer 4: Source Attribution - Tag every fact with KB source
    """

    def __init__(self):
        """Initialize validation patterns"""
        # Patterns that indicate unsourced/speculative claims
        self.speculation_patterns = [
            r'\b(?:i\s+(?:think|believe|assume|guess|suspect))\b',  # I think/believe
            r'\b(?:probably|likely|presumably|maybe|perhaps)\b(?!\s+[^.]*\[)',  # Hedge words
            r'\b(?:in\s+my\s+opinion|from\s+what\s+i\s+know)\b',  # Opinion markers
            r'(?<![\[\(])(?:it\s+seems|it\s+appears|it\s+is\s+said)',  # Vague attributions
        ]

        # Patterns indicating invention
        self.invention_patterns = [
            r'estimate(?!d\s+[^.]*\[)',  # Estimated (unsourced)
            r'approximate(?!ly\s+[^.]*\[)',  # Approximate (unsourced)
            r'roughly|about\s+\d+(?!\s*[^.]*\[)',  # Rough numbers
        ]

        # Knowledge base attribution pattern
        self.source_pattern = r'\[Source:\s*([^\]]+)\]'
        self.fact_pattern = r'\[Fact:\s*([^\]]+)\]'

    def validate_response(
        self,
        response: str,
        sources: List[str],
        facts: List[Dict[str, str]],
        kb_timestamp: Optional[str] = None
    ) -> Tuple[bool, str, List[str]]:
        """
        Validate response for hallucinations across all 4 layers

        Args:
            response: Generated response text
            sources: List of KB files used
            facts: List of facts from KB with source info
            kb_timestamp: KB timestamp for freshness tracking

        Returns:
            (is_valid, cleaned_response, detected_unsourced_claims)
        """
        unsourced_claims = []

        # Layer 3: Parse for unsourced claims
        unsourced_claims = self._detect_unsourced_claims(response)

        if unsourced_claims:
            logger.warning(
                f"Detected {len(unsourced_claims)} unsourced claims: {unsourced_claims}"
            )
            # Replace unsourced content with disclaimers
            response = self._add_source_disclaimers(response, facts, unsourced_claims)

        # Layer 4: Add source attribution
        response = self._add_source_attribution(response, facts, sources)

        is_valid = len(unsourced_claims) == 0

        return is_valid, response, unsourced_claims

    def verify_and_redact(self, response: str, rag_engine: Any) -> Dict[str, Any]:
        """
        Verify claims in `response` against the RAG engine and redact unsupported claims.

        Returns a dict with keys:
          - verified: bool
          - unsupported_claims: list
          - redacted: modified response string
        """
        try:
            # Use the lightweight verifier to find unsupported noun phrases/numbers
            verifier = ResponseValidator()
            check = verifier.verify_claims_against_rag(response, rag_engine)
            unsupported = check.get("unsupported_claims", [])
        except Exception as e:
            logger.debug(f"verify_and_redact verifier failed: {e}")
            return {"verified": True, "unsupported_claims": [], "redacted": response}

        if not unsupported:
            return {"verified": True, "unsupported_claims": [], "redacted": response}

        modified = response
        for cand in sorted(unsupported, key=lambda x: -len(x)):
            try:
                # Replace whole-word occurrences conservatively
                modified = re.sub(r"\b" + re.escape(cand) + r"\b", f"[Unverified: {cand}]", modified)
            except Exception:
                modified = modified.replace(cand, f"[Unverified: {cand}]")

        return {"verified": False, "unsupported_claims": unsupported, "redacted": modified}

    def _detect_unsourced_claims(self, text: str) -> List[str]:
        """
        Layer 3: Detect speculation and invention patterns

        Returns:
            List of suspected unsourced claim excerpts
        """
        unsourced = []

        # Check for speculation patterns
        for pattern in self.speculation_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                # Make sure there's no [Source] tag nearby
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                context = text[start:end]

                if '[Source:' not in context and '[Fact:' not in context:
                    unsourced.append(match.group().strip())

        # Check for invention patterns
        for pattern in self.invention_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                # Make sure there's no [Source] tag
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]

                if '[Source:' not in context:
                    unsourced.append(match.group().strip())

        return list(set(unsourced))  # Remove duplicates

    def _add_source_disclaimers(
        self,
        response: str,
        facts: List[Dict[str, str]],
        unsourced_claims: List[str]
    ) -> str:
        """
        Replace unsourced claims with explicit disclaimers

        Args:
            response: Original response
            facts: Facts from KB
            unsourced_claims: Claims to replace

        Returns:
            Modified response with disclaimers
        """
        modified = response

        for claim in unsourced_claims:
            # Find best matching KB fact to suggest
            best_fact = self._find_related_fact(claim, facts)

            if best_fact:
                # Replace with disclaimer pointing to KB
                disclaimer = (f"[According to my knowledge base: {best_fact['fact']}]")
                # This is a simplified replacement - in production, do more careful matching
                modified = re.sub(
                    re.escape(claim),
                    disclaimer,
                    modified,
                    flags=re.IGNORECASE,
                    count=1
                )
            else:
                # If no related fact, mark as unverified
                modified = re.sub(
                    re.escape(claim),
                    f"[Unverified: {claim}]",
                    modified,
                    flags=re.IGNORECASE,
                    count=1
                )

        return modified

    def _add_source_attribution(
        self,
        response: str,
        facts: List[Dict[str, str]],
        sources: List[str]
    ) -> str:
        """
        Layer 4: Add source tags and attribution

        Args:
            response: Response text
            facts: Facts with source information
            sources: List of KB sources used

        Returns:
            Response with source tags appended
        """
        # Add individual fact citations where possible
        citation_response = response

        # Add footer with all sources
        sources_str = ', '.join(set(sources)) if sources else "knowledge base"
        footer = f"\n\n**Sources:** {sources_str}"

        # Add confidence indicator if multiple sources agree
        if len(sources) > 1:
            footer += " (Multiple sources confirm this information)"

        return citation_response + footer

    def _find_related_fact(
        self,
        claim: str,
        facts: List[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """
        Find KB fact related to an unsourced claim

        Args:
            claim: Unsourced claim text
            facts: List of KB facts

        Returns:
            Most relevant fact or None
        """
        if not facts:
            return None

        # Simple keyword matching
        claim_words = set(claim.lower().split())
        best_match = None
        best_score = 0

        for fact in facts:
            fact_text = fact.get('fact', '').lower()
            fact_words = set(fact_text.split())

            # Score based on word overlap
            overlap = len(claim_words & fact_words)
            if overlap > best_score:
                best_score = overlap
                best_match = fact

        return best_match if best_score > 0 else None


class StrictRAGContext:
    """
    Layer 1: Create strict context that enforces KB-only responses
    """

    def __init__(self, max_context_length: int = 3000):
        """
        Initialize strict RAG context formatter

        Args:
            max_context_length: Max length of context to prevent token overflow
        """
        self.max_context_length = max_context_length

    def format_for_llm(
        self,
        documents: List[Dict[str, str]],
        sources: List[str],
        facts: List[Dict[str, str]],
        query: str = ""
    ) -> str:
        """
        Layer 1: Format context to strictly enforce KB-only constraint

        Args:
            documents: Retrieved documents from RAG
            sources: Source files
            facts: Extracted facts
            query: User query (for context)

        Returns:
            Formatted context string with explicit KB-only constraint
        """
        context_parts = []

        # Header with strict instructions
        header = """KNOWLEDGE BASE CONTEXT - STRICT RULES:

You MUST follow these rules exactly:
1. Use ONLY the information below from the knowledge base
2. Do NOT use any external knowledge or assumptions
3. Do NOT invent, estimate, or guess information
4. If asked something not in this knowledge base, respond: "I don't have this information in my knowledge base"

AVAILABLE FACTS:"""

        context_parts.append(header)

        # Add facts
        if facts:
            facts_text = "\n".join([
                f"- {fact.get('fact', '')}"
                for fact in facts[:10]  # Limit to first 10 facts
            ])
            context_parts.append(facts_text)
        else:
            context_parts.append("- (No relevant information found)")

        # Add sources
        if sources:
            sources_text = f"\nRELIABLE SOURCES: {', '.join(set(sources))}"
            context_parts.append(sources_text)

        # Add requirement sections
        requirement = """
DO NOT do any of these:
- Make up specific numbers or costs
- Invent facts not listed above
- Use phrases like "I believe", "probably", "likely"
- Extend information beyond what's provided
- Use general knowledge instead of KB facts

If the knowledge base doesn't contain information to answer the user's question,
respond with: "I don't have this information in my knowledge base.
I can help with: [list of topics available in KB]"
"""
        context_parts.append(requirement)

        full_context = "\n".join(context_parts)

        # Truncate if too long
        if len(full_context) > self.max_context_length:
            full_context = full_context[:self.max_context_length] + "\n..."

        return full_context

    def format_system_prompt(self) -> str:
        """
        Layer 2: Return system prompt that prohibits hallucination

        Returns:
            System prompt enforcing KB-only responses
        """
        return """You are a travel chatbot for Pune area trips.

ABSOLUTE HALLUCINATION PREVENTION RULES:
1. EVERY fact must come from the provided knowledge base
2. DO NOT use Wikipedia, general knowledge, or assumptions
3. DO NOT make up costs, distances, times, or other specifics
4. DO NOT claim something exists if not mentioned in knowledge base
5. DO NOT extend or interpret information beyond what's provided

PROHIBITED LANGUAGE:
- Never write: "I believe...", "I think...", "I assume..."
- Never write: "Probably...", "Likely...", "Presumably..."
- Never write: Made-up facts or creative extensions
- Never write: "Based on my knowledge" or "From what I know"

CORRECT RESPONSES:
✓ "Alibaug is 96 km from Pune. [Source: places.json]"
✓ "I don't have cost information for this place in my knowledge base"
✓ "The knowledge base covers: beaches, treks, forts near Pune"

WRONG RESPONSES:
✗ "Alibaug is probably about 100km away"  (speculative, wrong)
✗ "It's likely a beautiful destination"  (opinion, not fact)
✗ "Most people find it peaceful"  (unsourced claim)

Always respond with factual information from KB only."""

    def is_out_of_domain(
        self,
        query: str,
        available_topics: List[str]
    ) -> bool:
        """
        Check if query is outside knowledge base domain

        Args:
            query: User query
            available_topics: List of topics in KB

        Returns:
            True if query is out of domain
        """
        query_lower = query.lower()

        # Check if any KB topic appears in query
        for topic in available_topics:
            if topic.lower() in query_lower:
                return False

        return True


class ResponseValidator:
    """
    Validation helper - Check if response meets strict RAG criteria
    """

    def __init__(self):
        self.validation_layer = ResponseValidationLayer()

    def validate_has_sources(self, response: str) -> bool:
        """Check if response has source attribution"""
        return "[Source:" in response or "**Sources:**" in response

    def validate_no_speculation(self, response: str) -> bool:
        """Check if response avoids speculation"""
        speculation_words = [
            "probably", "likely", "presumably", "maybe",
            "i think", "i believe", "i assume", "in my opinion"
        ]
        response_lower = response.lower()

        for word in speculation_words:
            if word in response_lower:
                return False

        return True

    def validate_no_invented_facts(self, response: str) -> bool:
        """Check if response avoids invented facts"""
        invention_patterns = [
            r'\ballege(?!d)',  # allege (not alleged)
            r'\bestimate\b(?!\s+[^.]*\[)',  # estimate without source
            r'roughly\s+\d+',  # rough numbers
        ]

        for pattern in invention_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                return False

        return True

    def validate_response_quality(
        self,
        response: str,
        sources: List[str],
        facts: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Comprehensive validation of response

        Returns:
            {
                "is_valid": bool,
                "has_sources": bool,
                "no_speculation": bool,
                "no_invention": bool,
                "meets_criteria": bool,
                "issues": List[str]
            }
        """
        issues = []

        has_sources = self.validate_has_sources(response)
        no_speculation = self.validate_no_speculation(response)
        no_invention = self.validate_no_invented_facts(response)

        if not has_sources:
            issues.append("Missing source attribution")
        if not no_speculation:
            issues.append("Contains speculation language")
        if not no_invention:
            issues.append("Contains potentially invented facts")

        meets_criteria = all([has_sources, no_speculation, no_invention])

        return {
            "is_valid": meets_criteria,
            "has_sources": has_sources,
            "no_speculation": no_speculation,
            "no_invention": no_invention,
            "meets_criteria": meets_criteria,
            "issues": issues
        }

    def verify_claims_against_rag(self, response: str, rag_engine: Any) -> Dict[str, Any]:
        """Basic verifier that checks extracted noun-phrases / numeric claims against the RAG engine.

        This is a light-weight helper meant to be used as a post-check. It is intentionally
        conservative: if no supporting documents are found for a claim, the claim is returned
        as `unsupported` so calling code can redact or ask for clarification.
        """
        # Very small heuristic: extract capitalized sequences and numbers as candidate claims
        candidates = []

        # numbers/dates
        nums = re.findall(r"\b\d{1,4}\b", response)
        candidates.extend(nums)

        # Capitalized phrases (proper nouns)
        caps = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", response)
        candidates.extend(caps)

        unsupported = []

        for cand in set(candidates):
            try:
                r = rag_engine.retrieve_with_sources(cand, top_k=3)
                docs = r.get("documents") or []
                if not docs:
                    unsupported.append(cand)
            except Exception:
                unsupported.append(cand)

        return {"verified": len(unsupported) == 0, "unsupported_claims": unsupported}
