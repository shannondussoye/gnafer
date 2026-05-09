import os
import json
from typing import Optional
from ollama import Client
from src.models import ParsedAddress
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")

client = Client(host=OLLAMA_HOST)

SYSTEM_PROMPT = """
You are a precision Australian address parser. 
Extract components into a JSON object: unit, number, street, street_type, suburb, state, postcode.

RULES:
- STREET: Name only, UPPERCASE (e.g. "GEORGE", "GREAT WESTERN").
- STREET_TYPE: Standard abbreviation (ST, RD, AVE, HWY, BVD, PL, etc).
- NUMBER: Full number or range (e.g. "123", "10-12").
- UNIT: Include descriptors (e.g. "UNIT 5", "SHOP 3", "LEVEL 2", "THE PENTHOUSE").
- STATE: Abbreviation (NSW, VIC, QLD, WA, SA, TAS, ACT, NT).
- If missing, use null.
- Return ONLY the JSON object.
"""

def parse_address_llm(address_string: str) -> Optional[ParsedAddress]:
    """
    Parse an address string using Ollama (Qwen2.5).
    """
    try:
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': f"Parse this address: {address_string}"}
            ],
            format='json',
            options={'temperature': 0}
        )
        
        content = response['message']['content']
        if "</think>" in content:
            content = content.split("</think>")[-1].strip()
            
        data = json.loads(content)
        
        # Mapping and cleaning
        cleaned = {}
        mapping = {"street_name": "street", "locality": "suburb"}
        for k, v in data.items():
            key = mapping.get(k.lower(), k.lower())
            if isinstance(v, str):
                cleaned[key] = v.upper().strip()
            else:
                cleaned[key] = v

        valid_keys = ParsedAddress.model_fields.keys()
        final_data = {k: v for k, v in cleaned.items() if k in valid_keys}

        return ParsedAddress(**final_data)
    except Exception:
        # Silently fail for waterfall; errors will be handled in main loop logging (Phase 6)
        return None

if __name__ == "__main__":
    test_cases = [
        "Unit 5, Level 2, 10-12 Main Road, North Sydney, NSW 2060",
        "Shop 3, 123-125 Great Western Highway, Parramatta 2150",
        "The Penthouse, 1 George Street, Sydney"
    ]
    
    for tc in test_cases:
        parsed = parse_address_llm(tc)
        print(f"Input: {tc}")
        print(f"Parsed: {parsed}\n")
