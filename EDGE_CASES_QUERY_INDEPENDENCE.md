# Edge Case Analysis - Query Independence & Context Switching

## Problem Identification

### Case 1: Date Planning Query (User's Example)
```
User: "plan a date with my girlfriend in an aesthetic cafe in pune..."
Bot: [WRONG] Confirmed Mulshi Lake if inerary
Expected: [Either reject as social activity, OR recognize as romantic getaway trip]
Issue: Treated new query as continuation of hiking trip
```

### Case 2: Vulgar/Frustration Input
```
User: "the fuck"
Bot: Asked for trip details again
Expected: Recognize as frustration/gibberish, NOT a query
Issue: Not detecting emotional language / frustration markers
```

### Case 3: Query Type Switching
```
User: Hiking query → Date planning query → Gibberish
Bot: Mixed all three together
Expected: Handle each independently, reset state between different query types
Issue: No "query separation detection"
```

### Case 4: Multi-Activity Romantic Query
```
User: "cafe + nearby location for chilling and makeouts"
Bot: Couldn't parse (too ambiguous)
Expected: Recognize as "romantic getaway destination with cafe + activities"
Issue: No activity-type classification layer
```

---

## Root Causes

1. **No Query Independence Detection**
   - When user says something completely different, should reset state
   - Currently carries over previous conversation state

2. **Limited Query Type Classification**
   - Only detects: generic travel, hiking, beach, mountain
   - Doesn't classify: romantic dates, family trips, adventure sports, etc.
   - Doesn't reject: clearly non-travel activities

3. **State Management Issues**
   - `self.state` persists even when query type changes
   - `self.current_intent` doesn't get cleared between different activity types
   - Confirmation state applies to wrong queries

4. **No Emotional Language Detection**
   - "the fuck", "damn", "ugh" = frustration, not queries
   - Should be handled differently from gibberish

5. **No Clarification Logic**
   - Ambiguous queries get forced through existing pipeline
   - Should ask for clarification instead of guessing

---

## Solution Architecture: 8-Layer Enhanced System

### Layer 0: Emotional/Frustration Detection (NEW)
```python
def is_frustration_or_emotion(query: str) -> bool:
    """Detect if query is expressing frustration/emotion, not actual request"""
    frustration_words = ["fuck", "damn", "shit", "ugh", "argh", "why", "help"]
    stand_alone_curses = ["the fuck", "what the fuck", "fuck this", "damn it"]
    
    if any(curse in query.lower() for curse in stand_alone_curses):
        return True
    if query.strip() in frustration_words:
        return True
    return False
```

### Layer 1: Query Type Classification (ENHANCED)
```python
def classify_query_type(query: str) -> str:
    """Classify what type of trip/activity the user is asking for"""
    types = {
        "hiking": ["trek", "hike", "mountain", "peak", "trail"],
        "romantic": ["date", "girlfriend", "boyfriend", "romantic", "couple", "makeout"],
        "family": ["family", "kids", "children", "parents"],
        "adventure": ["adventure", "extreme", "adventure sports", "paragliding"],
        "beach": ["beach", "sea", "coastal", "ocean"],
        "heritage": ["heritage", "history", "ancient", "temple", "fort"],
        "budget": ["budget", "cheap", "affordable", "backpack"],
        "luxury": ["luxury", "5-star", "resort", "premium"],
        "business": ["business", "conference", "meeting", "work trip"],
        "cafe": ["cafe", "coffee", "restaurant", "food"],
    }
    
    query_lower = query.lower()
    detected_types = []
    
    for trip_type, keywords in types.items():
        if any(kw in query_lower for kw in keywords):
            detected_types.append(trip_type)
    
    return detected_types  # Multiple types possible: romantic + adventure
```

### Layer 1b: Query Independence Detection (NEW)
```python
def is_query_independent(current_query: str, previous_intent: Any) -> bool:
    """Check if current query is completely different from previous"""
    
    if not previous_intent:
        return True  # First query
    
    # Get current query type
    current_types = classify_query_type(current_query)
    
    # Check if shares ANY keywords with previous intent
    previous_types = []
    if previous_intent.interests:
        previous_types.extend(previous_intent.interests)
    if previous_intent.destination:
        previous_types.append(previous_intent.destination)
    
    # If NO overlap in types, it's independent
    if not any(t in previous_types for t in current_types):
        return True
    
    # Check for explicit trip type keywords that indicate new trip
    new_trip_indicators = ["also", "now", "next", "different", "instead", "but"]
    if any(indicator in current_query.lower() for indicator in new_trip_indicators):
        return True
    
    return False
```

### Layer 1c: Clarification Detection (NEW)
```python
def needs_clarification(query: str, query_type: list) -> tuple[bool, str]:
    """Check if query needs clarification"""
    
    # Ambiguous queries that need user to choose
    if "romantic" in query_type and "trip" not in query_type:
        # They're asking about date, not a trip
        return True, "Are you looking for a romantic getaway TRIP to a destination, or just activity suggestions for Pune?"
    
    if "cafe" in query_type and "trip" not in query_type:
        # They're asking about cafe, not a trip
        return True, "Are you looking for places to visit for a romantic date, or a trip with cafe/dining experiences?"
    
    if len(query_type) > 3:
        # Too many overlapping types
        return True, "Your request has multiple aspects. Please clarify: Are you looking for a (1) hiking trip, (2) romantic getaway, or (3) city cafe exploration?"
    
    return False, ""
```

### Layer 2: Activity Type Filtering (NEW)
```python
def is_travel_trip_query(query: str, query_types: list) -> bool:
    """Check if query is actually a TRAVEL TRIP, not just activity/social"""
    
    # These are NOT travel trip queries
    non_travel_activities = {
        "cafe": "cafe/restaurant suggestions",
        "dating": "dating advice",
        "restaurant": "restaurant reviews",
        "food": "food recommendations",
    }
    
    # If query is ONLY about non-travel activities, reject
    if len(query_types) == 1 and query_types[0] in non_travel_activities:
        return False
    
    # If query mentions "cafe" but also mentions destination/trip/duration, it's a trip
    if "cafe" in query_types and any(t in query_types for t in ["trip", "destination", "getaway"]):
        return True
    
    # Check for actual travel keywords
    travel_keywords = ["trip", "destination", "travel", "visit", "getaway", "itinerary", "days", "nights"]
    if any(kw in query.lower() for kw in travel_keywords):
        return True
    
    return False
```

### Layer 3: State Reset Decision (NEW)
```python
def should_reset_state(current_query: str, previous_state: str) -> bool:
    """Decide if we should reset conversation state"""
    
    if not previous_state or previous_state == "suggestion":
        return False  # Normal flow, no reset needed
    
    # If in confirmation state and user asks completely different query
    if previous_state == "confirmation":
        # Check for new inquiry patterns
        new_inquiry_patterns = [
            "plan",  # "plan a [different thing]"
            "suggest",  # "suggest a [different thing]"
            "what about",  # "what about [different thing]"
            "can you",  # "can you [different thing]"
        ]
        
        if any(pattern in current_query.lower() for pattern in new_inquiry_patterns):
            return True
    
    return False
```

### Layer 4-7: (Existing 5-layer defense system)

---

## Implementation Changes to chatbot.py

### 1. Add New Methods
```python
def is_frustration_or_emotion(self, query: str) -> bool:
    """Layer 0: Detect frustration/emotion"""
    # Implementation above

def classify_query_type(self, query: str) -> list:
    """Layer 1: Classify query type"""
    # Implementation above

def is_query_independent(self, query: str) -> bool:
    """Layer 1b: Check if independent from previous"""
    # Implementation above

def needs_clarification(self, query: str, query_types: list) -> tuple[bool, str]:
    """Layer 1c: Check if needs clarification"""
    # Implementation above

def is_travel_trip_query(self, query: str, query_types: list) -> bool:
    """Layer 2: Check if actually a travel trip"""
    # Implementation above

def should_reset_state(self, query: str) -> bool:
    """Layer 3: Decide if state needs reset"""
    # Implementation above
```

### 2. Modify handle_suggestion_flow()
```python
def handle_suggestion_flow(self, user_input: str):
    """ENHANCED with query independence & type classification"""
    
    # NEW Layer 0: Emotional detection
    if self.is_frustration_or_emotion(user_input):
        self.print_bot_msg(
            "I sense some frustration! 😅 That's okay. "
            "Take your time and let me know what kind of trip you'd like to plan."
        )
        self.history.append({"role": "Bot", "content": "Detected frustration"})
        return
    
    # NEW Layer 1: Query type classification
    query_types = self.classify_query_type(user_input)
    
    # NEW Layer 1b: Query independence check
    is_independent = self.is_query_independent(user_input, self.current_intent)
    
    if is_independent and self.current_intent:
        # NEW: Reset state for new query type
        self.state = "suggestion"
        self.current_intent = None
        self.selected_destination = None
        self.current_suggestions = []
        # Tell user we're starting fresh
        self.print_bot_msg("Got it! Let me help you plan a new adventure. 🗺️")
    
    # NEW Layer 1c: Clarification check
    needs_clarif, clarif_msg = self.needs_clarification(user_input, query_types)
    if needs_clarif:
        self.print_bot_msg(clarif_msg)
        self.history.append({"role": "Bot", "content": "Requested clarification"})
        return
    
    # NEW Layer 2: Check if actually a travel trip
    if not self.is_travel_trip_query(user_input, query_types):
        self.print_bot_msg(
            "I'm specialized in planning travel TRIPS! 🧳\n"
            "Your query sounds like you want local activity suggestions rather than a destination trip.\n"
            "Try: 'Plan a romantic getaway to a place with nice cafes' or 'Suggest a destination for a date trip'"
        )
        self.history.append({"role": "Bot", "content": "Non-travel activity detected"})
        return
    
    # NEW Layer 3: Check if should reset state
    if self.should_reset_state(user_input):
        self.state = "suggestion"
        self.current_intent = None
        self.selected_destination = None
        self.current_suggestions = []
        self.print_bot_msg("Starting a new trip plan! 🌟")
    
    # CONTINUE with existing 5-layer defense layers...
    # (gibberish, out-of-scope, info-only, intent extraction, validation)
```

---

## Test Cases to Cover

### Romantic/Date Queries
```
1. "plan a date with girlfriend in pune"
   → Should reject as non-travel or ask clarification

2. "plan a romantic getaway destination for 2 days"
   → Should accept (trip + romantic)

3. "cafe in pune with my girlfriend"
   → Should ask: "Are you looking for destination suggestions or cafe recommendations?"

4. "I want to go on a romantic trip for a weekend with nice restaurants and cafes"
   → Should accept (trip + romantic + activities)
```

### Frustration/Emotion
```
1. "the fuck"
   → "I sense frustration! What trip can I help you plan?"

2. "this is bullshit"
   → "Seems like something's wrong. Tell me what trip you'd like planned."

3. "argh why won't you understand"
   → "Sorry for the confusion! Tell me about your ideal trip."
```

### Query Switching
```
1. [Hiking query] → [Date query] → [Beach query]
   → Each should reset state properly

2. [First query in confirmation state] + [New query]
   → Should reset and start fresh
```

### Multi-Activity Queries
```
1. "adventure trek + romantic cafe experience"
   → Ask: Are you looking for (1) adventure trek, or (2) romantic getaway?

2. "family trip with kids and trekking"
   → Accept (combines family + adventure)

3. "budget backpacking + luxury resorts"
   → Ask: "Which is it - budget or luxury?"
```

---

## Expected Outcomes After Implementation

### Before
```
User: "plan a date with girlfriend in cafe..."
Bot: "🎉 Confirmed Mulshi Lake hiking trip" ❌ WRONG

User: "the fuck"
Bot: "Tell me trip details..." ❌ WRONG
```

### After
```
User: "plan a date with girlfriend in cafe..."
Bot: "Are you looking for a romantic getaway to a destination, 
      or local cafe suggestions?" OR
      "Perfect! I can suggest romantic destinations. 
       What's your budget and duration?" ✅ CORRECT

User: "the fuck"
Bot: "I sense frustration! What trip would you like to plan?" ✅ CORRECT

User: "hiking trip" → "date planning" → "check nearby"
Bot: 
  1. Plans hiking ✅
  2. Resets state: "Got it! New adventure! Let's plan a romantic trip" ✅
  3. Plans date getaway ✅
```

---

## Summary: 3 Critical Improvements

1. **Query Independence Detection**: When user asks something completely different, reset state
2. **Query Type Classification**: Identify different trip types (romantic, family, adventure, etc.)
3. **Clarification Logic**: When ambiguous, ask user to clarify instead of guessing wrongly
4. **Frustration Detection**: Recognize emotional language, don't treat it as queries
5. **State Management**: Reset conversation state when switching between different trip types

This prevents the chatbot from:
- Confirming wrong itineraries
- Mixing up query contexts
- Treating frustration as queries
- Forcing ambiguous queries into wrong categories
