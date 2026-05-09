import os
import json
from typing import Optional
from ollama import Client
from src.models import ParsedAddress
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:7b")

client = Client(host=OLLAMA_HOST)

SYSTEM_PROMPT = """
You are an expert Australian address parser. Your task is to extract structured components from a given address string.
Always return the result as a JSON object matching this schema:
{
    "unit": "string or null",
    "number": "string or null",
    "street": "string or null",
    "street_type": "string or null (e.g., ST, RD, AVE)",
    "suburb": "string or null",
    "state": "string or null (e.g., NSW, VIC, QLD)",
    "postcode": "string or null"
}
Convert street names to UPPERCASE. Convert street types to standard abbreviations (ST, RD, AVE, etc.).
Only return the JSON object. No preamble or explanation.
"""

def parse_address_llm(address_string: str) -> Optional[ParsedAddress]:
    """
    Parse an address string using Ollama/Deepseek (Fallback for Qwen2.5).
    Used as a fallback for complex or ambiguous addresses.
    """
    try:
        response = client.generate(
            model=OLLAMA_MODEL,
            system=SYSTEM_PROMPT,
            prompt=f"Parse this Australian address: {address_string}",
            format='json',
            options={'temperature': 0} # Deterministic output
        )
        
        data = json.loads(response['response'])
        return ParsedAddress(**data)
    except Exception as e:
        # In a production environment, we would log this to Logtail
        print(f"LLM Parsing Error: {e}")
        return None

if __name__ == "__main__":
    # Test cases for complex addresses
    test_cases = [
        "Unit 5, Level 2, 10-12 Main Road, North Sydney, NSW 2060",
        "Shop 3, 123-125 Great Western Highway, Parramatta 2150",
        "The Penthouse, 1 George Street, Sydney"
    ]
    
    for tc in test_cases:
        parsed = parse_address_llm(tc)
        print(f"Input: {tc}")
        print(f"Parsed: {parsed}\n")
