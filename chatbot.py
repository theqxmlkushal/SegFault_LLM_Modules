"""
WanderAI Conversational Chatbot - Full End-to-End with Zero Hallucination
State-aware conversation with multi-option selection and booking
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load .env
load_dotenv()

from modules.m0_query_refiner import QueryRefiner
from modules.m1_intent_extractor import IntentExtractor
from modules.m2_destination_suggester import DestinationSuggester
from modules.m3_itinerary_builder import ItineraryBuilder
from modules.m6_place_description_generator import PlaceDescriptionGenerator
from utils.rag_engine import SimpleRAG

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WanderAIChatbot:
    def __init__(self):
        self.refiner = QueryRefiner()
        self.extractor = IntentExtractor()
        self.suggester = DestinationSuggester()
        self.builder = ItineraryBuilder()
        self.desc_gen = PlaceDescriptionGenerator()
        self.rag = SimpleRAG()
        
        self.history: List[Dict[str, str]] = []
        self.current_intent: Optional[Any] = None
        self.current_suggestions: List[Any] = []
        self.selected_destination: Optional[Any] = None
        self.state: str = "suggestion"  # suggestion, selection, confirmation

    def get_history_string(self) -> str:
        return "\n".join([f"{h['role']}: {h['content']}" for h in self.history[-4:]])

    def print_bot_msg(self, msg: str):
        print(f"\n✨ WanderAI: {msg}")

    def is_destination_grounded(self, destination_name: str) -> bool:
        """Check if destination exists in KB to prevent hallucination."""
        try:
            docs = self.rag.search(destination_name, top_k=1)
            return bool(docs and "No relevant documents found" not in str(docs))
        except Exception:
            return False

    def is_gibberish_or_spam(self, user_input: str) -> bool:
        """Detect gibberish, spam, or meaningless input."""
        user_lower = user_input.lower().strip()
        
        # Too short
        if len(user_lower) < 3:
            return True
        
        # Only special characters or repeated characters
        alpha_numeric = [c for c in user_lower if c.isalnum()]
        if len(alpha_numeric) < 3:
            return True
        
        # Mostly repeated same character (spam)
        if len(set(user_lower)) < 3:
            return True  # "aaaaa", "xxxxx", "!!!!!!"
        
        # Whitelist of legitimate travel/currency words that shouldn't be flagged
        # These are common words that happen to have many letters from single QWERTY row
        whitelist_words = {
            "rupees", "rupee", "euros", "euro", "pounds", "dollars",
            "yen", "currency", "budget", "trip", "trek", "beach",
            "mountain", "river", "temple", "restaurant", "hotel"
        }
        
        # QWERTY keyboard rows for detection
        qwerty_patterns = {
            "qwerty": "qwertyuiop",
            "asdf": "asdfghjkl",
            "zxcv": "zxcvbnm"
        }
        
        # Check if mostly keyboard row letters (like "asdfhjk", "qwertyu", etc)
        words = user_lower.split()
        for word in words:
            clean_word = ''.join(c for c in word if c.isalpha())
            
            if len(clean_word) < 4:
                continue
            
            # Skip whitelisted words
            if clean_word in whitelist_words:
                continue
            
            # Check if word is MOSTLY made of consecutive keyboard keys
            for row_pattern, full_row in qwerty_patterns.items():
                # Count how many letters are from this keyboard row
                from_row = sum(1 for c in clean_word if c in full_row)
                if from_row / len(clean_word) > 0.8:  # 80%+ from one row
                    return True
        
        # Check for completely random letter sequences with vowel but no meaning
        # Like "xyz", "abc" - these are alphabet sequences
        alphabet = "abcdefghijklmnopqrstuvwxyz"
        for word in words:
            clean_word = ''.join(c for c in word if c.isalpha())
            
            if 3 <= len(clean_word) <= 5:
                # Check if it's a sequential alphabet subset
                # "abc", "xyz", "def" etc.
                for i in range(len(alphabet) - len(clean_word) + 1):
                    substr = alphabet[i:i+len(clean_word)]
                    if clean_word == substr:
                        # This is sequential alphabet, not a real word
                        return True
        
        return False

    def is_purely_interrogative(self, query: str) -> bool:
        """Check if query is purely asking for info (not planning a trip)."""
        # Queries that are about places but not trip planning
        pure_info_keywords = [
            "what is", "tell me about", "information about",
            "history of", "capital of", "population of",
            "how many", "when was", "why is", "how far is"
        ]
        
        # Trip planning keywords that override info queries
        trip_keywords = [
            "plan", "trip", "travel", "visit", "go to",
            "trek", "hike", "getaway", "weekend", "itinerary",
            "budget", "days", "suggest", "recommend"
        ]
        
        query_lower = query.lower()
        
        # If has trip keywords, not purely interrogative
        if any(kw in query_lower for kw in trip_keywords):
            return False
        
        # If purely asking for info
        if any(kw in query_lower for kw in pure_info_keywords):
            return True
        
        return False

    def validate_extracted_intent(self, intent: Any) -> tuple[bool, str]:
        """Validate if extracted intent is meaningful and coherent."""
        try:
            # Check if intent has at least SOME meaningful data
            has_interests = intent.interests and len(intent.interests) > 0
            has_duration = intent.duration_days and intent.duration_days > 0
            has_group = intent.group_size and intent.group_size > 0
            
            # Missing all fields
            if not (has_interests or has_duration or has_group):
                return False, "No meaningful travel parameters extracted"
            
            # Check for impossible values
            if has_duration and intent.duration_days > 365:
                return False, "Trip duration seems unrealistic (>365 days)"
            
            if has_group and intent.group_size > 100:
                return False, "Group size seems too large (>100 people)"
            
            # Check for nonsense interests
            interests = intent.interests or []
            nonsense_interests = ["gibberish", "random", "asdf", "xyz", "test"]
            if any(i.lower() in nonsense_interests for i in interests):
                return False, "Could not extract meaningful interests"
            
            # Valid intent
            return True, "Intent is valid"
            
        except Exception as e:
            return False, f"Error validating intent: {str(e)}"

    def is_out_of_scope(self, user_input: str) -> bool:
        """Detect if query is clearly out-of-scope (not travel-related)."""
        # Travel keywords that should NOT be filtered
        travel_keywords = [
            "trek", "hike", "travel", "trip", "destination", "place",
            "visit", "explore", "beach", "mountain", "hill", "fort",
            "weekend", "itinerary", "plan", "suggest", "getaway"
        ]
        
        # Only filter queries that are completely non-travel
        out_of_scope_keywords = [
            "joke", "meme", "recipe", "cook", "cooking", "code", "programming",
            "math", "politics", "sports", "movie", "music", "song", "love",
            "marry", "poem", "story", "book"
        ]
        
        user_lower = user_input.lower()
        
        # If contains travel keywords, it's definitely in scope
        if any(kw in user_lower for kw in travel_keywords):
            return False
        
        # If contains out-of-scope keywords, reject it
        if any(keyword in user_lower for keyword in out_of_scope_keywords):
            return True
        
        # Default: be permissive for ambiguous queries
        return False

    def has_travel_intent(self, refined_query: str) -> bool:
        """Check if refined query indicates actual travel intent."""
        # Positive indicators of travel intent
        travel_keywords = [
            "plan", "trek", "destination", "place", "trip", "travel",
            "itinerary", "suggest", "weekend", "beach", "mountain",
            "fort", "hike", "visit", "explore", "getaway", "escape"
        ]
        
        # Strong negative indicators
        no_travel_indicators = [
            "no travel intent",
            "does not contain any travel",
            "not related to travel",
            "error", "failed", "unable to"
        ]
        
        refined_lower = refined_query.lower()
        
        # If positive travel keywords present, it's travel intent
        if any(kw in refined_lower for kw in travel_keywords):
            return True
        
        # If strong negative indicators, it's NOT travel intent
        if any(indicator in refined_lower for indicator in no_travel_indicators):
            return False
        
        # Default to True for ambiguous cases (be permissive)
        return True

    def run(self):
        print("\n" + "="*50)
        print("   WanderAI Conversational Assistant")
        print("="*50 + "\n")
        self.print_bot_msg("Hey! 👋 Tell me what you're thinking for your next trip. I can suggest places, describe them, and build itineraries!")

        while True:
            user_input = input("\n> ").strip()
            
            # Exit conditions
            if user_input.lower() in ['exit', 'quit', 'bye', 'goodbye']:
                self.print_bot_msg("Happy travels! Goodbye! ✈️")
                break
            
            # Empty input
            if not user_input:
                self.print_bot_msg("Please enter a query (e.g., 'Plan a trip to Lonavala')")
                continue

            # Route based on current state
            if self.state == "selection":
                self.handle_selection_state(user_input)
            elif self.state == "confirmation":
                self.handle_confirmation_state(user_input)
            else:
                # Normal suggestion flow
                self.handle_suggestion_flow(user_input)

    def handle_suggestion_flow(self, user_input: str):
        """Handle normal suggestion flow with comprehensive edge case handling."""
        
        # Edge Case 0: Gibberish/Spam Detection
        if self.is_gibberish_or_spam(user_input):
            self.print_bot_msg(
                "I didn't quite understand that. Could you please ask clearly about a travel destination or trip? "
                "For example: 'Plan a trek this weekend' or 'Suggest a beach destination'"
            )
            self.history.append({"role": "Bot", "content": "Gibberish detected"})
            return
        
        # Edge Case 1: Out-of-scope keywords detected upfront
        if self.is_out_of_scope(user_input):
            self.print_bot_msg(
                "I'm specialized in travel planning! 😊 Ask me about destinations, itineraries, or things to do near Pune. "
                "For example: 'Plan a trip for a romantic getaway' or 'What's a good beach near Pune?'"
            )
            self.history.append({"role": "Bot", "content": "Out of scope query rejected"})
            return
        
        # Edge Case 1b: Purely interrogative (info request, not trip planning)
        if self.is_purely_interrogative(user_input):
            self.print_bot_msg(
                "I can answer travel questions, but I'm best at helping you PLAN trips! 😊 "
                "Try asking: 'Plan a trip to Alibaug' or 'Suggest a destination for a weekend getaway'"
            )
            self.history.append({"role": "Bot", "content": "Purely interrogative query"})
            return
        
        # 1. Refine Query with Context
        history_str = self.get_history_string()
        try:
            structured = self.refiner.refine_structured(user_input, history_str)
            refined_query = structured.get("refined") if isinstance(structured, dict) else str(structured)
            flags = structured.get("flags", {}) if isinstance(structured, dict) else {}
        except Exception as e:
            logger.warning(f"Refiner failed: {e}")
            refined_query = user_input
            flags = {}

        # Edge Case 2: Refiner detected no travel intent
        if not self.has_travel_intent(refined_query):
            self.print_bot_msg(
                "I'm specialized in travel planning! 😊 Ask me about destinations, itineraries, or things to do near Pune. "
                "For example: 'Plan a trip for a romantic getaway' or 'What's a good beach near Pune?'"
            )
            self.history.append({"role": "Bot", "content": "No travel intent detected"})
            return

        # Edge Case 3: Critical budget constraint
        if flags.get("critical_budget"):
            self.print_bot_msg(
                "It looks like your requested budget is insufficient for the requested duration. "
                "Please increase the budget, shorten the trip, or provide a destination."
            )
            self.history.append({"role": "Bot", "content": "Budget rejected: insufficient"})
            return
        
        self.history.append({"role": "User", "content": user_input})
        
        # 2. Extract Intent
        try:
            intent = self.extractor.extract(refined_query)
            self.current_intent = intent
        except Exception as e:
            logger.error(f"Intent extraction failed: {e}")
            self.print_bot_msg("I had trouble understanding your request. Could you rephrase?")
            return
        
        # Edge Case 4: Intent has no meaningful criteria
        if not intent or (not intent.interests and not intent.budget and not intent.duration_days):
            self.print_bot_msg(
                "To help me suggest the best destinations, please provide at least one of: "
                "interests (beach, trek, history), budget, or duration. "
                "For example: 'I want a beach trip for 2 days with ₹5000 budget'"
            )
            return        
        # Edge Case 4b: Validate extracted intent for coherence
        is_valid, validation_msg = self.validate_extracted_intent(intent)
        if not is_valid:
            self.print_bot_msg(
                f"I had trouble understanding: {validation_msg}. "
                "Could you be more specific? Try: 'Beach trip for 2 days' or 'Trek with 5k budget'"
            )
            return        
        # 3. Suggest Multiple Destinations (all grounded in KB)
        try:
            suggestions = self.suggester.suggest(intent, top_k=5)
        except Exception as e:
            logger.error(f"Suggestion failed: {e}")
            self.print_bot_msg("I encountered an issue retrieving suggestions. Please try again.")
            return
        
        # Edge Case 5: No destinations returned
        if not suggestions or not suggestions.destinations:
            self.print_bot_msg(
                "I couldn't find any suggestions for your criteria. "
                "Could you relax your constraints or provide more details?"
            )
            return
        
        # Filter out hallucinated destinations (only KB-grounded)
        grounded_dests = [
            dest for dest in suggestions.destinations
            if self.is_destination_grounded(dest.name)
        ]
        
        # Edge Case 6: No grounded destinations after filtering
        if not grounded_dests:
            self.print_bot_msg(
                "I couldn't find destinations in my knowledge base matching your criteria. "
                "Could you provide more specific details (e.g., beach, trek, city, heritage)?"
            )
            self.history.append({"role": "Bot", "content": "No grounded destinations found"})
            return
        
        # Store suggestions and display options
        self.current_suggestions = grounded_dests[:3]
        self.display_options(self.current_suggestions, intent)
        self.state = "selection"
        self.history.append({"role": "Bot", "content": f"Suggested {len(self.current_suggestions)} grounded options"})

    def handle_selection_state(self, user_input: str):
        """Handle user selecting from options with NATURAL LANGUAGE support.
        
        Accepts:
        - Numeric: "1", "2", "3"
        - Positional: "first", "second", "third", "last"
        - Name-based: "lake", "mulshi", "beach destination"
        - Random: "surprise me", "random pick", "dealer's choice"
        - Skip: "none of these", "show me options again"
        - Fallback: Any other input → clarify original query
        """
        user_lower = user_input.lower().strip()
        
        # Handle explicit rejections (re-show options)
        if any(phrase in user_lower for phrase in ["none of these", "show again", "show options", "list again", "all bad"]):
            self.display_options(self.current_suggestions, self.current_intent)
            return
        
        # Handle random/surprise selection
        if any(phrase in user_lower for phrase in ["surprise", "random", "dealer's choice", "pick for me", "choose", "you decide"]):
            import random
            choice = random.randint(0, len(self.current_suggestions) - 1)
            self.selected_destination = self.current_suggestions[choice]
            self._build_and_confirm_itinerary()
            return
        
        # Try numeric input first
        try:
            choice = int(user_input.strip())
            if 1 <= choice <= len(self.current_suggestions):
                self.selected_destination = self.current_suggestions[choice - 1]
                self._build_and_confirm_itinerary()
                return
            else:
                self.print_bot_msg(f"Please enter a number between 1 and {len(self.current_suggestions)}")
                return
        except ValueError:
            pass  # Not a number, try other methods
        
        # Try positional keywords (first, second, third, etc.)
        positional_map = {
            "first": 0, "1st": 0, "one": 0,
            "second": 1, "2nd": 1, "two": 1,
            "third": 2, "3rd": 2, "three": 2,
            "last": len(self.current_suggestions) - 1
        }
        
        for word, idx in positional_map.items():
            if word in user_lower:
                if 0 <= idx < len(self.current_suggestions):
                    self.selected_destination = self.current_suggestions[idx]
                    self._build_and_confirm_itinerary()
                    return
        
        # Try destination name matching
        for i, dest in enumerate(self.current_suggestions):
            dest_name_lower = dest.name.lower()
            # Check if destination name is mentioned
            if dest_name_lower in user_lower or user_lower in dest_name_lower:
                self.selected_destination = dest
                self._build_and_confirm_itinerary()
                return
            # Check for partial match (lake, beach, mountain, etc. in the name)
            words = user_lower.split()
            dest_words = dest_name_lower.split()
            if any(w in dest_name_lower for w in words if len(w) > 3):
                self.selected_destination = dest
                self._build_and_confirm_itinerary()
                return
        
        # Try location type matching (beach, trek, mountain, lake, etc.)
        location_preferences = {
            "beach": ["beach", "sea", "coastal", "ocean", "shore"],
            "mountain": ["mountain", "hill", "trek", "hiking", "peak"],
            "lake": ["lake", "water", "dam", "reservoir"],
            "city": ["city", "urban", "town"],
            "adventure": ["adventure", "trek", "hike", "trek"],
        }
        
        user_words = user_lower.split()
        for pref_type, keywords in location_preferences.items():
            if any(kw in user_lower for kw in keywords):
                # Try to find destination that matches this preference
                for i, dest in enumerate(self.current_suggestions):
                    if any(kw in dest.name.lower() for kw in keywords):
                        self.selected_destination = dest
                        self._build_and_confirm_itinerary()
                        return
        
        # Smart fallback: If user input looks like they're trying to refine or ask something new
        if any(phrase in user_lower for phrase in ["but", "instead", "what if", "tell me", "why", "how", "can we"]):
            self.print_bot_msg(
                f"Got it! Let me help you refine. You wanted a trip based on: {self._format_intent()}.\n\n"
                f"Would you like to:\n"
                f"1. Modify your trip details (budget/duration/interests)\n"
                f"2. See the destination options again\n"
                f"3. Get descriptions for each option"
            )
            return
        
        # Fallback: User might be trying to start a new query entirely
        if len(user_input.split()) > 3 or any(word in user_lower for word in ["plan", "suggest", "find", "want"]):
            self.print_bot_msg(
                "I understand you might want to try something different! "
                f"Your current options are: {', '.join([d.name for d in self.current_suggestions])}.\n\n"
                f"Would you like to:\n"
                f"1. Pick one of these destinations (say the name or number)\n"
                f"2. Modify your trip and get new suggestions"
            )
            return
        
        # Generic fallback with helpful guidance
        self.print_bot_msg(
            f"I'm not sure which destination you mean. Your options are:\n\n"
            f"{', '.join([f'{i+1}. {d.name}' for i, d in enumerate(self.current_suggestions)])}\n\n"
            f"Try saying: '1' or 'the first one' or '{self.current_suggestions[0].name.split()[0].lower()}' or 'surprise me'"
        )

    def _build_and_confirm_itinerary(self):
        """Helper method to build and display itinerary after destination selection."""
        self.current_suggestions = []
        
        # Build itinerary
        self.print_bot_msg(f"Perfect! Building your {self.selected_destination.name} itinerary...")
        try:
            itinerary = self.builder.build(self.current_intent, self.selected_destination)
            self.display_itinerary(itinerary)
            self.state = "confirmation"
            self.print_bot_msg("Does this itinerary look good? (yes/no/modify)")
            self.history.append({"role": "Bot", "content": f"Built itinerary for {self.selected_destination.name}"})
        except Exception as e:
            logger.error(f"Itinerary build failed: {e}")
            self.print_bot_msg("I encountered an issue building the itinerary. Let me show you other options.")
            self.state = "selection"
            for i, dest in enumerate(self.current_suggestions, 1):
                self.print_bot_msg(f"{i}. {dest.name}")

    def _format_intent(self) -> str:
        """Format intent for display in conversation."""
        parts = []
        if self.current_intent and self.current_intent.interests:
            parts.append(f"interested in {', '.join(self.current_intent.interests)}")
        if self.current_intent and self.current_intent.duration_days:
            parts.append(f"{self.current_intent.duration_days} days")
        if self.current_intent and self.current_intent.budget:
            parts.append(f"₹{self.current_intent.budget} budget")
        return " | ".join(parts) if parts else "a trip"

    def handle_confirmation_state(self, user_input: str):
        """Handle user confirmation of itinerary with CONVERSATIONAL flexibility.
        
        Accepts:
        - Yes: yes, y, confirm, good, looks good, perfect, great, love it
        - No: no, n, cancel, not good, try again, nope
        - Modify: modify, change, adjust, edit, different
        - Empty/Unclear: Ask clarification with context
        """
        user_lower = user_input.lower().strip()
        
        # Handle empty input
        if not user_lower:
            self.print_bot_msg(
                f"Does the {self.selected_destination.name} itinerary work for you?\n"
                "Please say: yes, no, or what you'd like to modify"
            )
            return
        
        # YES responses - Confirm booking
        yes_keywords = ['yes', 'y', 'confirm', 'good', 'looks good', 'perfect', 'great', 'love it', 'awesome', 'brilliant', 'let\'s go', 'book it', 'confirmed']
        if any(kw in user_lower for kw in yes_keywords):
            self.print_bot_msg(
                f"🎉 Booking confirmed for {self.selected_destination.name}!\n\n"
                "Your itinerary has been finalized. Safe travels! ✈️\n\n"
                "For support, contact: support@wanderai.com"
            )
            self.history.append({"role": "Bot", "content": "Booking confirmed"})
            self.state = "suggestion"
            self.selected_destination = None
            self.print_bot_msg("What else can I help you with? Plan another trip or ask for travel tips!")
            return
        
        # NO responses - Show alternatives
        no_keywords = ['no', 'n', 'cancel', 'not good', 'try again', 'nope', 'don\'t like', 'not quite', 'something else']
        if any(kw in user_lower for kw in no_keywords):
            self.print_bot_msg("No problem! Let me show you other options.")
            self.state = "selection"
            self.selected_destination = None
            self.display_options(self.current_suggestions, self.current_intent)
            self.history.append({"role": "Bot", "content": "Itinerary rejected, showing alternatives"})
            return
        
        # MODIFY responses
        modify_keywords = ['modify', 'change', 'adjust', 'edit', 'different', 'more days', 'less days', 'other', 'instead']
        if any(kw in user_lower for kw in modify_keywords):
            self.print_bot_msg(
                f"What would you like to modify? You can adjust:\n"
                f"- Duration (currently {self.current_intent.duration_days} days)\n"
                f"- Budget (currently ₹{self.current_intent.budget})\n"
                f"- Activities/Interests\n\n"
                f"Just let me know what you'd like to change!"
            )
            self.history.append({"role": "Bot", "content": "User requested modifications"})
            self.state = "suggestion"  # Go back to suggestion flow to refine
            return
        
        # Handle unclear/conversational responses
        if len(user_input.split()) > 2:
            self.print_bot_msg(
                f"I understand! Let me clarify - does the {self.selected_destination.name} itinerary work for you?\n"
                "Please reply: YES to book, NO to try alternatives, or MODIFY to adjust details"
            )
            return
        
        # Fallback for single words or unclear input
        self.print_bot_msg(
            f"I didn't quite understand. Is the {self.selected_destination.name} itinerary good?\n"
            "Please say: yes (book it), no (try others), or modify (adjust details)"
        )

    def display_options(self, destinations: List[Any], intent: Any):
        """Display multiple destination options with error handling."""
        msg = "🎯 Great! Here are my top recommendations based on your preferences:\n\n"
        
        for i, dest in enumerate(destinations, 1):
            try:
                description = self.desc_gen.generate(dest.name)
                desc_short = description[:120] + "..." if len(description) > 120 else description
            except Exception:
                desc_short = "Popular destination near Pune"
            
            msg += f"**{i}. {dest.name}**\n"
            msg += f"   📍 Distance: {dest.distance}\n"
            msg += f"   💰 Cost: {dest.estimated_cost}\n"
            msg += f"   ⭐ Match Score: {dest.match_score}%\n"
            msg += f"   📝 {desc_short}\n\n"
        
        msg += "Which option interests you most? (Enter 1, 2, or 3)"
        self.print_bot_msg(msg)

    def display_itinerary(self, itinerary):
        """Display formatted itinerary with all details."""
        if not itinerary or not itinerary.days:
            print("\n❌ Error: Invalid itinerary data")
            return
        
        print("\n" + "-"*50)
        print(f"📍 Destination: {itinerary.destination}")
        print(f"⏱️  Duration: {itinerary.duration} days")
        print(f"💰 Total Cost: {itinerary.total_estimated_cost}")
        print("-"*50)
        
        for day in itinerary.days:
            print(f"\nDAY {day.day}: {day.title}")
            if day.schedule:
                for slot in day.schedule:
                    print(f"  {slot.time} - {slot.activity} (@ {slot.location})")
        
        if itinerary.packing_list:
            print(f"\n🎒 Packing Essentials:")
            for item in itinerary.packing_list[:5]:
                print(f"   ✓ {item}")
        
        if itinerary.important_notes:
            print(f"\n⚠️  Important Notes:")
            for note in itinerary.important_notes[:3]:
                print(f"   • {note}")
        
        print("-"*50)

if __name__ == "__main__":
    bot = WanderAIChatbot()
    bot.run()