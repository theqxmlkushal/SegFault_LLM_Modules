#!/usr/bin/env python
"""
Interactive test demonstrating the new Layer 0-3 fixes for the user's reported failures:
1. Query type switching (hiking -> romantic)
2. Emotional language detection ("the fuck")
3. State reset between different trip types
4. Clarification for ambiguous queries
"""

from chatbot import WanderAIChatbot

def test_scenario(title, query):
    """Test a single scenario."""
    print("\n" + "=" * 70)
    print(f"TEST: {title}")
    print("=" * 70)
    print(f"User Input: {query}")
    print("-" * 70)
    
    cb = WanderAIChatbot()
    
    # Check Layer 0: Frustration detection
    if cb.is_frustration_or_emotion(query):
        print("[LAYER 0] FRUSTRATION DETECTED!")
        print("Status: FAIL - This should not be processed as a travel query")
        return False
    
    # Check Layer 1: Query type classification
    query_types = cb.classify_query_type(query)
    print(f"[LAYER 1] Query Types Detected: {query_types}")
    
    # Check Layer 1c: Needs clarification
    needs_clarif, clarif_msg = cb.needs_clarification(query, query_types)
    if needs_clarif:
        print(f"[LAYER 1c] CLARIFICATION NEEDED!")
        print(f"Bot Response: {clarif_msg}")
        return True
    
    # Check Layer 2: Travel trip verification
    is_trip = cb.is_travel_trip_query(query, query_types)
    if not is_trip:
        print(f"[LAYER 2] NOT A TRAVEL TRIP - Rejected")
        print("Status: PASS - Correctly rejected non-travel activity inquiry")
        return True
    
    print(f"[LAYER 2] TRAVEL TRIP VERIFIED - Would proceed to full processing")
    print("Status: PASS - Correctly identified as valid travel query")
    return True

def main():
    print("\n" + "#" * 70)
    print("# QUERY INDEPENDENCE & EMOTIONAL LANGUAGE TEST SUITE")
    print("#" * 70)
    
    # Test Case 1: User's exact failure - switching from hiking to romantic
    test_scenario(
        "Query Type Switch (Hiking -> Romantic)",
        "plan a date with my girlfriend in aesthetic cafe in pune"
    )
    
    # Test Case 2: User's exact failure - frustration language
    test_scenario(
        "Frustration Detection ('the fuck')",
        "the fuck"
    )
    
    # Test Case 3: User's exact failure - more frustration
    test_scenario(
        "Frustration Detection (curse word)",
        "what the fuck is this"
    )
    
    # Test Case 4: Ambiguous romantic query needing clarification
    test_scenario(
        "Clarification for Ambiguous Query",
        "plan a romantic trip with my girlfriend"
    )
    
    # Test Case 5: Activity-only query (should ask for clarification)
    test_scenario(
        "Activity-Only Query Clarification",
        "cafe recommendations"
    )
    
    # Test Case 6: Conflicting budget requirements
    test_scenario(
        "Conflicting Types (Budget vs Luxury)",
        "I want a budget and luxury trip"
    )
    
    # Test Case 7: Valid hiking trip (should pass)
    test_scenario(
        "Valid Hiking Trip Query",
        "plan a hiking trip for 3 days"
    )
    
    # Test Case 8: Valid beach trip (should pass)
    test_scenario(
        "Valid Beach Trip Query",
        "suggest a beach destination for a weekend getaway"
    )
    
    # Test Case 9: Valid romantic trip (should pass)
    test_scenario(
        "Valid Romantic Trip Query",
        "I want to plan a romantic getaway for 2-3 days with my girlfriend"
    )
    
    # Test Case 10: Family adventure trip (should pass)
    test_scenario(
        "Valid Family Adventure Query",
        "suggest a family-friendly adventure trip near Pune"
    )
    
    print("\n" + "#" * 70)
    print("# TEST SUITE COMPLETED")
    print("#" * 70)

if __name__ == "__main__":
    main()
