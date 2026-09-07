"""Scripted LLM boundary for repeatable integration tests.

This adapter returns structured LLM-like decisions. It is intentionally outside the
router and does not model production language understanding.
"""

from shopping_agent.llm.parsing import InputInterpretation, RequirementExtraction
from shopping_agent.schemas import Product, RequirementAssessment, UserRequirements


class ScriptedShoppingSemantics:
    def interpret_input(self, message: str, requirements: UserRequirements | None, products: list[Product], conversation_context: str = "") -> InputInterpretation:
        decisions = {
            "I want running shoes.": ("search", True, None),
            "Size 42, any brand, under $100.": ("change_requirements", True, None),
            "I want running shoes under $20, size 42.": ("search", True, None),
            "Okay, increase it to $80.": ("change_requirements", True, None),
            "Actually, I want something cheaper under $90.": ("change_requirements", True, None),
            "Show me more.": ("more_results", False, None),
            "I want the second one.": ("purchase", False, products[1].id if len(products) > 1 else None),
            "I prefer Nike.": ("change_requirements", True, None),
            "I'm finished.": ("finish", False, None),
        }
        intent, should_extract, selected = decisions[message]
        return InputInterpretation(intent=intent, should_extract_requirements=should_extract, selected_product_id=selected)

    def extract_requirements(self, message: str, current: UserRequirements | None) -> RequirementExtraction:
        entries = {
            "I want running shoes.": (UserRequirements(query="running shoes"), False, ["shoe size and a budget"], ["brand", "colour"]),
            "Size 42, any brand, under $100.": (UserRequirements(size="42", max_price=100, no_preference_fields=["brand"]), True, [], ["colour"]),
            "I want running shoes under $20, size 42.": (UserRequirements(query="running shoes", size="42", max_price=20), True, [], ["brand", "colour"]),
            "Okay, increase it to $80.": (UserRequirements(max_price=80), True, [], ["brand", "colour"]),
            "Actually, I want something cheaper under $90.": (UserRequirements(max_price=90), True, [], ["brand", "colour"]),
            "I prefer Nike.": (UserRequirements(preferred_brands=["Nike"]), True, [], ["colour"]),
        }
        patch, sufficient, missing, optional = entries[message]
        merged = current.model_copy(update={key: value for key, value in patch.model_dump().items() if value not in (None, [], {})}) if current else patch
        return RequirementExtraction(requirements=merged, assessment=RequirementAssessment(sufficient_for_search=sufficient, missing_required_information=missing, optional_preferences=optional))

    def write_clarification(self, assessment: RequirementAssessment, requirements: UserRequirements | None) -> str:
        if "relax" in assessment.missing_required_information[0]:
            return "I couldn't find running shoes at that price. Would you like to increase your budget?"
        return "What shoe size and maximum budget work for you? Brand is optional."
