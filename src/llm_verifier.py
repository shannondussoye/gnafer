"""LLM-based address verification.

Given an input address and a G-NAF candidate, asks a local LLM
whether they refer to the same physical address.
"""

import asyncio
import json
import logging

from ollama import AsyncClient

from src.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_RETRY_DELAY = 0.5  # seconds

VERIFY_SYSTEM_PROMPT = """You compare Australian addresses. Answer only with JSON: {"match": true} or {"match": false}.

Key rules:
- "1704/45" means Unit 1704, Number 45. This is the same as "UNIT 1704 45".
- Ignore building names like "MERITON SUITES" at the start.
- ST = STREET, RD = ROAD, AVE = AVENUE.
- Ignore case differences.
- Number ranges (e.g. "7-11") match if the input number falls within the range.
"""


class LLMVerifier:
    """Verify address matches using a local Ollama LLM."""

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
    ):
        self._model: str = model if model is not None else settings.ollama_model
        self._host: str = host if host is not None else settings.ollama_host
        self._async_client = AsyncClient(host=self._host)

    def _build_prompt(self, input_address: str, candidate_label: str) -> str:
        return (
            f"INPUT: {input_address}\n"
            f"CANDIDATE: {candidate_label}\n\n"
            f"Are these the same physical address?"
        )

    def _parse_response(self, content: str) -> bool:
        """Parse the LLM response JSON. Returns True if match confirmed."""
        try:
            data = json.loads(content)
            return bool(data.get("match", False))
        except (json.JSONDecodeError, AttributeError):
            logger.warning("LLM returned unparseable response: %s", content)
            return False

    async def verify_async(self, input_address: str, candidate_label: str) -> bool:
        """Ask the LLM if two addresses are the same (async).

        Retries up to ``_MAX_RETRIES`` times on transient failures.
        """
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await self._async_client.chat(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
                        {"role": "user", "content": self._build_prompt(input_address, candidate_label)},
                    ],
                    format="json",
                    options={"temperature": 0},
                )
                return self._parse_response(response["message"]["content"])
            except Exception:
                if attempt < _MAX_RETRIES:
                    logger.debug(
                        "LLM verification attempt %d failed for '%s' vs '%s', retrying...",
                        attempt + 1, input_address, candidate_label, exc_info=True,
                    )
                    await asyncio.sleep(_RETRY_DELAY * (attempt + 1))
                else:
                    logger.debug(
                        "LLM verification failed after %d attempts for '%s' vs '%s'",
                        _MAX_RETRIES + 1, input_address, candidate_label, exc_info=True,
                    )
                    return False
        return False  # unreachable, but satisfies type checkers

    async def verify_batch_async(
        self, pairs: list[tuple[str, str]], batch_size: int | None = None,
    ) -> list[bool]:
        """Verify multiple (input, candidate) pairs concurrently."""
        if batch_size is None:
            batch_size = settings.llm_batch_size
        results = []
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i : i + batch_size]
            tasks = [
                self.verify_async(input_addr, candidate)
                for input_addr, candidate in batch
            ]
            results.extend(await asyncio.gather(*tasks))
        return results

    async def check_available(self) -> bool:
        """Check if the Ollama server is reachable."""
        try:
            await self._async_client.list()
            return True
        except Exception:
            return False
