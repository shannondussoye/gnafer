"""Supabase client factory with lifecycle management.

Provides a plain client factory for backward compatibility and a context-managed
variant that guarantees proper shutdown of the auth refresh timer and the
underlying httpx session.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

import httpx
from httpx import Client as SyncHttpxClient
from httpx import HTTPTransport, Limits
from postgrest.exceptions import APIError
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from src.config import settings

logger = logging.getLogger(__name__)


def _is_retryable_error(exc: Exception) -> bool:
    """Determine whether an exception warrants a retry."""
    status: int | None = None
    if isinstance(exc, APIError):
        status = getattr(exc, "status_code", None)
        return status is None or status in (429, 503, 520)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response else None
    elif isinstance(exc, httpx.HTTPError):
        return True
    if status is not None:
        return status in (429, 503, 520)
    return "rate limit" in str(exc).lower()


def with_retry[T](
    operation: Callable[[], T],
    max_retries: int | None = None,
    base_delay_ms: float | None = None,
) -> T:
    """Execute *operation* with exponential backoff on transient failures.

    Parameters
    ----------
    operation
        Callable returning the desired value.
    max_retries
        Override for ``settings.supabase_max_retries``.
    base_delay_ms
        Override for ``settings.supabase_retry_base_delay_ms``.
    """
    max_retries = max_retries if max_retries is not None else settings.supabase_max_retries
    base_delay = base_delay_ms if base_delay_ms is not None else settings.supabase_retry_base_delay_ms

    for attempt in range(max_retries + 1):
        try:
            return operation()
        except Exception as exc:
            if not _is_retryable_error(exc) or attempt == max_retries:
                raise
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 200), 10000)
            logger.warning(
                "Supabase retryable error (attempt %d/%d), waiting %.0fms: %s",
                attempt + 1,
                max_retries + 1,
                delay,
                exc,
            )
            time.sleep(delay / 1000)

    raise RuntimeError("Unreachable")


def get_supabase_client() -> Client:
    """Create a sync Supabase client from centralised settings.

    .. note::
       For long-lived processes or batch pipelines, prefer
       :func:`managed_supabase_client` to avoid resource leaks.
    """
    url = settings.supabase_url
    key = settings.supabase_auth_key
    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) are required."
        )

    limits = Limits(
        max_connections=50,
        max_keepalive_connections=10,
        keepalive_expiry=30.0,
    )
    transport = HTTPTransport(http2=True, limits=limits)
    http = SyncHttpxClient(transport=transport, timeout=30.0)
    options = SyncClientOptions(httpx_client=http)

    return create_client(url, key, options=options)


@contextmanager
def managed_supabase_client() -> Any:
    """Yield a sync Supabase client with guaranteed shutdown.

    Ensures ``auth.sign_out()`` and ``httpx`` session closure on exit,
    preventing the known hang caused by the background auth refresh timer.
    """
    client = get_supabase_client()
    try:
        yield client
    finally:
        try:
            client.auth.sign_out()
        except Exception:
            logger.exception("Error during supabase sign_out")
        try:
            # Close the injected httpx session
            if hasattr(client, "_http_client"):
                client._http_client.close()
        except Exception:
            logger.exception("Error closing httpx client")


class SupabaseGeocodeClient:
    """Wrapper for Supabase fetch / writeback operations.

    .. deprecated::
       Prefer using :func:`managed_supabase_client` together with the
       helpers in :mod:`src.supabase_pipeline`.  This class is kept for
       backward compatibility with the existing ``run_supabase_batch`` flow.
    """

    def __init__(self, client: Client | None = None) -> None:
        self._client = client or get_supabase_client()
        self._table = settings.supabase_table
        self._pending = settings.supabase_status_pending
        self._processing = settings.supabase_status_processing
        self._completed = settings.supabase_status_completed
        self._failed = settings.supabase_status_failed
        self._fetch_chunk = settings.supabase_fetch_chunk
        self._upsert_chunk = settings.supabase_upsert_chunk

    def _fetch_page(self, start: int, end: int) -> list[dict[str, Any]]:
        """Fetch a single page of pending rows with retry."""

        def _do() -> list[dict[str, Any]]:
            response = (
                self._client.table(self._table)
                .select("*")
                .eq("status", self._pending)
                .order("id")
                .range(start, end)
                .execute()
            )
            return list(response.data)  # type: ignore[arg-type]

        return with_retry(_do)

    def fetch_pending(self, limit: int = 0) -> list[dict[str, Any]]:
        """Paginate through pending rows and return them all."""
        rows: list[dict[str, Any]] = []
        offset = 0
        chunk = self._fetch_chunk

        while True:
            page = self._fetch_page(offset, offset + chunk - 1)
            if not page:
                break
            rows.extend(page)
            if limit and len(rows) >= limit:
                rows = rows[:limit]
                break
            if len(page) < chunk:
                break
            offset += chunk

        logger.info("Fetched %d pending row(s) from Supabase.", len(rows))
        return rows

    def _mark_status(self, ids: list[Any], status: str) -> None:
        """Bulk-update status for a list of record IDs."""
        if not ids:
            return

        def _do() -> None:
            payload = [{"id": id_, "status": status} for id_ in ids]
            self._client.table(self._table).upsert(payload, default_to_null=False).execute()

        with_retry(_do)

    def mark_processing(self, ids: list[Any]) -> None:
        """Mark rows as processing to prevent double-work."""
        self._mark_status(ids, self._processing)
        logger.info("Marked %d row(s) as processing.", len(ids))

    def _upsert_chunk_with_retry(self, chunk: list[dict[str, Any]]) -> None:
        def _do() -> None:
            self._client.table(self._table).upsert(chunk, default_to_null=False).execute()

        with_retry(_do)

    def writeback_results(self, records: list[dict[str, Any]]) -> tuple[int, int]:
        """Chunked upsert of geocoded results.

        Returns
        -------
        tuple[int, int]
            (successful_chunks, failed_chunks)
        """
        successful = 0
        failed = 0
        chunk_size = self._upsert_chunk

        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            try:
                self._upsert_chunk_with_retry(chunk)
                successful += 1
                logger.debug("Upserted chunk of %d row(s).", len(chunk))
            except (APIError, httpx.HTTPError):
                logger.exception(
                    "Failed to upsert chunk after retries (rows %d-%d)",
                    i,
                    i + len(chunk) - 1,
                )
                failed += 1
                self._mark_failed(chunk)

        total = len(records)
        logger.info(
            "Writeback complete: %d row(s), %d chunk(s) succeeded, %d chunk(s) failed.",
            total,
            successful,
            failed,
        )
        return successful, failed

    def _mark_failed(self, chunk: list[dict[str, Any]]) -> None:
        """Best-effort mark of a failed chunk so they can be retried later."""
        try:
            ids = [r["id"] for r in chunk if "id" in r]
            if ids:
                payload = [{"id": id_, "status": self._failed} for id_ in ids]
                self._client.table(self._table).upsert(payload, default_to_null=False).execute()
        except (APIError, httpx.HTTPError):
            logger.exception("Failed to mark chunk as failed — manual cleanup may be needed.")
