"""GNAF Geocoder API.

FastAPI endpoints for single and batch address geocoding using
trigram matching with optional LLM verification.
"""

import asyncio
import functools
import logging
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.config import settings
from src.llm_verifier import LLMVerifier
from src.main import run_supabase_batch
from src.models import MatchResult
from src.observability import GeocoderObservability
from src.supabase_pipeline import run_pipeline
from src.trigram_matcher import TrigramAddressMatcher, get_connection_pool, load_street_types

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_matcher: TrigramAddressMatcher | None = None
_verifier: LLMVerifier | None = None
_obs: GeocoderObservability | None = None
_pool = None
_reaper_task: asyncio.Task | None = None

JOB_REAP_INTERVAL = 60  # seconds between cleanup sweeps


async def _reap_expired_jobs() -> None:
    """Periodically remove completed/failed jobs older than TTL."""
    while True:
        await asyncio.sleep(JOB_REAP_INTERVAL)
        now = time.time()
        expired = [
            jid for jid, job in jobs.items()
            if job.get("status") in ("completed", "failed")
            and now - job.get("completed_at", job.get("created_at", now)) > settings.job_ttl_seconds
        ]
        for jid in expired:
            del jobs[jid]
        if expired:
            logger.info("Reaped %d expired job(s) from store", len(expired))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _pool, _matcher, _verifier, _obs, _reaper_task

    # Use the unified connection pool factory (#14)
    _pool = get_connection_pool()

    _matcher = TrigramAddressMatcher(
        pool=_pool, abbreviations=load_street_types(settings.psv_path),
    )
    _verifier = LLMVerifier()
    _obs = GeocoderObservability()

    _reaper_task = asyncio.create_task(_reap_expired_jobs())

    yield

    if _reaper_task:
        _reaper_task.cancel()
    if _pool:
        _pool.closeall()


app = FastAPI(title="GNAF Geocoder API", version="2.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request tracing middleware
# ---------------------------------------------------------------------------


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """Attach a unique request_id to every request for end-to-end tracing."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestTracingMiddleware)

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class GeocodeRequest(BaseModel):
    address: str


class BatchGeocodeRequest(BaseModel):
    addresses: list[str] = Field(..., max_length=settings.max_batch_size)


class SupabaseBatchRequest(BaseModel):
    limit: int = Field(default=0, ge=0, description="Maximum rows to process (0 = all pending)")


class JobStatus(BaseModel):
    job_id: str
    status: str
    total: int
    processed: int
    successful: int
    progress_pct: float = 0.0


jobs: dict[str, dict] = {}
_jobs_lock = asyncio.Lock()

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check — verifies actual database connectivity (#11)."""
    if _pool is None:
        raise RuntimeError("Pool not initialized")
    conn = None
    try:
        conn = _pool.getconn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception:
        logger.exception("Health check failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    finally:
        if conn:
            _pool.putconn(conn)


@app.post("/geocode", response_model=MatchResult)
async def geocode_single(request: GeocodeRequest) -> MatchResult:
    """Geocode a single address."""
    if _matcher is None:
        raise RuntimeError("Matcher not initialized")
    # Run blocking match in executor to avoid blocking the event loop (#9)
    loop = asyncio.get_running_loop()
    match = await loop.run_in_executor(None, _matcher.match, request.address)

    if match.similarity_score == 0:
        raise HTTPException(status_code=404, detail=f"Could not geocode: {request.address}")

    # LLM verification if in threshold band
    if settings.llm_verify_threshold <= match.similarity_score < 1.0:
        try:
            if _verifier is None:
                raise RuntimeError("Verifier not initialized")
            if await _verifier.verify_async(match.input_address, match.address_label):
                match = match.model_copy(update={
                    "similarity_score": 1.0,
                    "llm_verified": True,
                    "match_method": "TRIGRAM+LLM",
                })
        except ConnectionError:
            logger.debug("LLM server unreachable", exc_info=True)
        except TimeoutError:
            logger.debug("LLM verification timed out", exc_info=True)
        except Exception:
            logger.debug("LLM verification failed", exc_info=True)

    if match.match_method is None:
        match.match_method = "TRIGRAM"

    return match


async def _process_batch(job_id: str, addresses: list[str]) -> None:
    """Background worker for batch geocoding."""
    if _matcher is None:
        raise RuntimeError("Matcher not initialized")
    if _verifier is None:
        raise RuntimeError("Verifier not initialized")
    if _obs is None:
        raise RuntimeError("Observability not initialized")

    try:
        # Run blocking match_batch in executor (#9)
        loop = asyncio.get_running_loop()
        matches = await loop.run_in_executor(
            None,
            functools.partial(
                _matcher.match_batch,
                addresses,
                workers=settings.trigram_workers,
                show_progress=False,
            ),
        )
        jobs[job_id]["processed"] = len(addresses)

        # LLM verification
        pending = [
            (i, m) for i, m in enumerate(matches)
            if settings.llm_verify_threshold <= m.similarity_score < 1.0
        ]
        if pending:
            try:
                if await _verifier.check_available():
                    pairs = [(m.input_address, m.address_label) for _, m in pending]
                    verdicts = await _verifier.verify_batch_async(pairs)
                    for (idx, match), verdict in zip(pending, verdicts, strict=True):
                        if verdict:
                            matches[idx] = match.model_copy(update={
                                "similarity_score": 1.0,
                                "llm_verified": True,
                                "match_method": "TRIGRAM+LLM",
                            })
            except ConnectionError:
                logger.debug("LLM server unreachable during batch verification", exc_info=True)
            except Exception:
                logger.debug("Batch LLM verification failed", exc_info=True)

        for m in matches:
            if m.match_method is None:
                m.match_method = "TRIGRAM" if m.similarity_score > 0 else "FAILED"
            jobs[job_id]["results"].append(m.model_dump())
            if m.similarity_score > 0:
                jobs[job_id]["successful"] += 1

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["completed_at"] = time.time()
        _obs.log_completion({"job_id": job_id, "total": len(addresses), "successful": jobs[job_id]["successful"]})

    except Exception:
        logger.exception("Batch processing failed for job %s", job_id)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["completed_at"] = time.time()


@app.post("/geocode/batch")
async def geocode_batch(request: BatchGeocodeRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Start a batch geocoding job (#10 — enforces max_batch_size via model validation)."""
    # Enforce max store size to prevent unbounded memory growth
    async with _jobs_lock:
        if len(jobs) >= settings.job_max_store_size:
            raise HTTPException(
                status_code=429,
                detail=f"Job store full ({settings.job_max_store_size} jobs). Wait for existing jobs to expire.",
            )

        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "status": "processing",
            "total": len(request.addresses),
            "processed": 0,
            "successful": 0,
            "results": [],
            "created_at": time.time(),
        }
    background_tasks.add_task(_process_batch, job_id, request.addresses)
    return {"job_id": job_id, "message": "Batch job started"}


def _run_supabase_batch_sync(limit: int) -> dict[str, int]:
    """Sync wrapper so the async pipeline can be dispatched in a thread executor."""
    return asyncio.run(run_supabase_batch(workers=settings.trigram_workers, limit=limit))


async def _process_supabase_batch(job_id: str, limit: int) -> None:
    """Background worker for Supabase batch geocoding."""
    try:
        loop = asyncio.get_running_loop()
        summary = await loop.run_in_executor(
            None, functools.partial(_run_supabase_batch_sync, limit=limit),
        )
        jobs[job_id]["processed"] = summary["total"]
        jobs[job_id]["successful"] = summary["success"]
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["completed_at"] = time.time()
    except Exception:
        logger.exception("Supabase batch processing failed for job %s", job_id)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["completed_at"] = time.time()


@app.post("/geocode/supabase")
async def geocode_supabase(request: SupabaseBatchRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Start a Supabase pipeline job using the new supabase_pipeline module."""
    if not settings.supabase_url or not settings.supabase_auth_key:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    async with _jobs_lock:
        if len(jobs) >= settings.job_max_store_size:
            raise HTTPException(
                status_code=429,
                detail=f"Job store full ({settings.job_max_store_size} jobs). Wait for existing jobs to expire.",
            )

        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "status": "processing",
            "total": 0,
            "processed": 0,
            "successful": 0,
            "results": [],
            "created_at": time.time(),
        }

    async def _worker() -> None:
        try:
            stats = await asyncio.to_thread(run_pipeline, limit=request.limit if request.limit > 0 else None)
            jobs[job_id]["total"] = stats["pulled"]
            jobs[job_id]["processed"] = stats["geocoded"]
            jobs[job_id]["successful"] = stats["written"]
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["completed_at"] = time.time()
        except Exception:
            logger.exception("Supabase pipeline failed for job %s", job_id)
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["completed_at"] = time.time()

    background_tasks.add_task(_worker)
    return {"job_id": job_id, "message": "Supabase pipeline started"}


@app.post("/geocode/supabase-batch")
async def geocode_supabase_batch(request: SupabaseBatchRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Start a Supabase batch geocoding job."""
    if not settings.supabase_url or not settings.supabase_key:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    async with _jobs_lock:
        if len(jobs) >= settings.job_max_store_size:
            raise HTTPException(
                status_code=429,
                detail=f"Job store full ({settings.job_max_store_size} jobs). Wait for existing jobs to expire.",
            )

        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "status": "processing",
            "total": 0,
            "processed": 0,
            "successful": 0,
            "results": [],
            "created_at": time.time(),
        }
    background_tasks.add_task(_process_supabase_batch, job_id, request.limit)
    return {"job_id": job_id, "message": "Supabase batch job started"}


@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str) -> JobStatus:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    pct = (job["processed"] / job["total"] * 100) if job["total"] > 0 else 0
    return JobStatus(job_id=job_id, progress_pct=pct, **{k: job[k] for k in ("status", "total", "processed", "successful")})


@app.get("/jobs/{job_id}/results")
async def get_job_results(job_id: str) -> dict[str, object]:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "status": jobs[job_id]["status"], "results": jobs[job_id].get("results", [])}
