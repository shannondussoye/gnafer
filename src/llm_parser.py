import os
import json
import asyncio
from ollama import AsyncClient, Client
from src.models import ParsedAddress
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

SYSTEM_PROMPT = """
You are a specialist Australian address parser. 
Extract components from the input address into a JSON object.
Rules:
- Convert street types to standard abbreviations (ST, RD, AVE, etc.).
- Handle unit numbers (unit), level/floor numbers (level), and shop numbers correctly.
- Hierarchical fields (unit, level) should contain ONLY the identifier (e.g., "5", "G", "UG"), not the words "Unit", "Level", or "Floor".
- If a range is given (e.g., 123-125), put the first number in 'number'.
- Return ONLY valid JSON.

Fields: unit, level, number, street, street_type, suburb, state, postcode.
"""

async def parse_address_llm_async(address: str) -> ParsedAddress:
    """Parse address using Ollama asynchronously."""
    client = AsyncClient(host=OLLAMA_HOST)
    try:
        response = await client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': address}
            ],
            format='json',
            options={'temperature': 0}
        )
        
        data = json.loads(response['message']['content'])
        # Add input_address back for model compatibility
        data['input_address'] = address
        return ParsedAddress(**data)
    except Exception as e:
        # Graceful failure for LLM errors
        return None

def parse_address_llm(address: str) -> ParsedAddress:
    """Parse address using Ollama synchronously."""
    client = Client(host=OLLAMA_HOST)
    try:
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': address}
            ],
            format='json',
            options={'temperature': 0}
        )
        data = json.loads(response['message']['content'])
        data['input_address'] = address
        return ParsedAddress(**data)
    except Exception:
        return None
