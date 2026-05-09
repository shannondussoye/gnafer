from typing import Optional, Tuple
from src.models import ParsedAddress
from src.simple_parser import parse_address_simple
from src.llm_parser import parse_address_llm

def parse_address(address_string: str) -> Tuple[Optional[ParsedAddress], str]:
    """
    Waterfall parsing strategy:
    1. Try simple Regex parsing (Fast).
    2. If Regex fails, try LLM parsing (Slower, but robust).
    
    Returns a tuple of (ParsedAddress, method_used).
    """
    # Stage 1: Regex
    parsed = parse_address_simple(address_string)
    if parsed:
        return parsed, "REGEX"
    
    # Stage 2: LLM Fallback
    parsed = parse_address_llm(address_string)
    if parsed:
        return parsed, "LLM"
    
    return None, "FAILED"

if __name__ == "__main__":
    # Test waterfall
    test_cases = [
        "123 George St, Sydney NSW 2000", # Should be REGEX
        "Level 5, 10 Main Rd, Melbourne 3000", # Should be LLM (due to 'Level 5')
    ]
    
    for tc in test_cases:
        parsed, method = parse_address(tc)
        print(f"Input: {tc}")
        print(f"Method: {method}")
        print(f"Parsed: {parsed}\n")
