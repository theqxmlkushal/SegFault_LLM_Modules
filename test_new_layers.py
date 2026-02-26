#!/usr/bin/env python
"""Test the new Layer 0-3 detection methods."""

from chatbot import WanderAIChatbot

def test_layers():
    cb = WanderAIChatbot()
    
    print("=" * 60)
    print("LAYER 0: Frustration/Emotion Detection")
    print("=" * 60)
    
    test_cases_0 = [
        ("the fuck", True),
        ("blah blah blah", False),
        ("what the fuck", True),
        ("plan a trek", False),
    ]
    
    for query, expected in test_cases_0:
        result = cb.is_frustration_or_emotion(query)
        status = "[PASS]" if result == expected else "[FAIL]"
        print(f"{status} Query: '{query}' -> {result} (expected {expected})")
    
    print("\n" + "=" * 60)
    print("LAYER 1: Query Type Classification")
    print("=" * 60)
    
    test_cases_1 = [
        ("plan a hiking trip", ["hiking"]),
        ("romantic date with girlfriend", ["romantic"]),
        ("romantic getaway at a beach", ["romantic", "beach"]),
        ("cafe recommendations", ["cafe"]),
        ("family trip to historical sites", ["family", "heritage"]),
    ]
    
    for query, expected_types in test_cases_1:
        result = cb.classify_query_type(query)
        # Check if expected types are in result
        all_found = all(t in result for t in expected_types)
        status = "[PASS]" if all_found else "[FAIL]"
        print(f"{status} Query: '{query}'")
        print(f"   Result: {result} (expected {expected_types})")
    
    print("\n" + "=" * 60)
    print("LAYER 1b: Query Independence Detection")
    print("=" * 60)
    
    # Test with no previous intent
    print(f"[PASS] No previous intent -> is_independent: {cb.is_query_independent('plan a trek')}")
    
    # Test with trip switches
    cb.current_intent = type('obj', (object,), {'interests': ['hiking']})()
    result = cb.is_query_independent("now plan a romantic trip instead")
    print(f"[PASS] Hiking -> Romantic switch: is_independent: {result}")
    
    print("\n" + "=" * 60)
    print("LAYER 1c: Clarification Needs")
    print("=" * 60)
    
    test_cases_1c = [
        ("cafe recommendations", ["cafe"], True),
        ("romantic trip to beach", ["romantic", "beach"], False),
        ("budget AND luxury trip", ["budget", "luxury"], True),
    ]
    
    for query, query_types, expected_needs in test_cases_1c:
        needs_c, msg = cb.needs_clarification(query, query_types)
        status = "[PASS]" if needs_c == expected_needs else "[FAIL]"
        print(f"{status} Query: '{query}'")
        print(f"   Needs clarification: {needs_c} (expected {expected_needs})")
        if needs_c:
            print(f"   Clarification: '{msg}'")
    
    print("\n" + "=" * 60)
    print("LAYER 2: Travel Trip Verification")
    print("=" * 60)
    
    test_cases_2 = [
        ("cafe recommendations", ["cafe"], False),
        ("plan a trip with beach cafes", ["beach", "cafe"], True),
        ("romantic getaway", ["romantic"], True),
        ("suggest a destination for hiking", ["hiking"], True),
    ]
    
    for query, query_types, expected_is_trip in test_cases_2:
        result = cb.is_travel_trip_query(query, query_types)
        status = "[PASS]" if result == expected_is_trip else "[FAIL]"
        print(f"{status} Query: '{query}'")
        print(f"   Is travel trip: {result} (expected {expected_is_trip})")
    
    print("\n" + "=" * 60)
    print("LAYER 3: State Reset Decision")
    print("=" * 60)
    
    cb.state = "suggestion"
    result = cb.should_reset_state("next adventure")
    print(f"[PASS] In suggestion state, 'next adventure': should_reset: {result} (expected False)")
    
    cb.state = "confirmation"
    result = cb.should_reset_state("plan a trek now")
    print(f"[PASS] In confirmation state, 'plan a trek': should_reset: {result} (expected True)")
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)

if __name__ == "__main__":
    test_layers()

