import asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import uuid
import time
from src.matcher import AddressMatcher
from src.simple_parser import parse_address_simple
from src.llm_parser import parse_address_llm_async
from src.models import GeocodedResult
from src.observability import GeocoderObservability

app = FastAPI(title="GNAF Geocoder API", version="1.0.0")

# Shared resources
matcher = AddressMatcher()
obs = GeocoderObservability()

class GeocodeRequest(BaseModel):
    address: str

class BatchGeocodeRequest(BaseModel):
    addresses: List[str]

class JobStatus(BaseModel):
    job_id: str
    status: str
    total: int
    processed: int
    successful: int
    progress_pct: float = 0.0

JOB_TTL_SECONDS = 3600

@app.on_event("startup")
async def start_job_cleanup():
    asyncio.create_task(cleanup_expired_jobs())

async def cleanup_expired_jobs():
    while True:
        await asyncio.sleep(300)
        now = time.time()
        expired = [
            jid for jid, job in jobs.items()
            if job.get("completed_at") and (now - job["completed_at"]) > JOB_TTL_SECONDS
        ]
        for jid in expired:
            del jobs[jid]

# In-memory job store (In production, use Redis/DB)
jobs = {}

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "database": "connected"}

@app.post("/geocode", response_model=GeocodedResult)
async def geocode_single(request: GeocodeRequest, min_confidence: float = 0.0):
    """Geocode a single address using the high-performance waterfall."""
    addr = request.address
    
    # 1. Regex Pass
    parsed = parse_address_simple(addr)
    if parsed:
        match = matcher.match(parsed)
        if match and match.confidence >= min_confidence:
            match.parse_method = "REGEX"
            obs.log_progress("Single Geocode Success", {
                "address": addr,
                "method": "REGEX",
                "confidence": match.confidence,
                "match_type": match.match_type
            })
            return match
            
    # 2. LLM Pass (Async)
    parsed = await parse_address_llm_async(addr)
    if parsed:
        match = matcher.match(parsed)
        if match and match.confidence >= min_confidence:
            match.parse_method = "LLM"
            obs.log_progress("Single Geocode Success", {
                "address": addr,
                "method": "LLM",
                "confidence": match.confidence,
                "match_type": match.match_type
            })
            return match
            
    # 3. Failure
    obs.log_progress("Single Geocode Failed", {"address": addr})
    raise HTTPException(status_code=404, detail=f"Could not geocode address: {addr}")

async def process_batch_job(job_id: str, addresses: List[str]):
    """Background worker for batch geocoding."""
    pending_llm = []
    
    # --- Pass 1: Regex ---
    for addr in addresses:
        parsed = parse_address_simple(addr)
        if parsed:
            match = matcher.match(parsed)
            if match:
                match.parse_method = "REGEX"
                jobs[job_id]["results"].append(match.model_dump())
                jobs[job_id]["processed"] += 1
                jobs[job_id]["successful"] += 1
                continue
        pending_llm.append(addr)
        jobs[job_id]["processed"] += 1

    obs.log_progress("Batch Job Started", {"job_id": job_id, "total": len(addresses)})

    # --- Pass 2: LLM (In batches) ---
    BATCH_SIZE = 15
    for i in range(0, len(pending_llm), BATCH_SIZE):
        batch = pending_llm[i:i + BATCH_SIZE]
        tasks = [parse_address_llm_async(addr) for addr in batch]
        parsed_batch = await asyncio.gather(*tasks)
        
        for addr, parsed in zip(batch, parsed_batch):
            if parsed:
                match = matcher.match(parsed)
                if match:
                    match.parse_method = "LLM"
                    jobs[job_id]["results"].append(match.model_dump())
                    jobs[job_id]["successful"] += 1
            # We don't increment "processed" here because we did it in Pass 1
        
    jobs[job_id]["status"] = "completed"
    jobs[job_id]["completed_at"] = time.time()
    
    obs.log_completion({
        "job_id": job_id,
        "total": len(addresses),
        "successful": jobs[job_id]["successful"]
    })
    obs.ping_healthcheck()

@app.post("/geocode/batch")
async def geocode_batch(request: BatchGeocodeRequest, background_tasks: BackgroundTasks):
    """Start a batch geocoding job in the background."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "processing",
        "total": len(request.addresses),
        "processed": 0,
        "successful": 0,
        "results": []
    }
    
    background_tasks.add_task(process_batch_job, job_id, request.addresses)
    
    return {"job_id": job_id, "message": "Batch job started"}

@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Check the status of a background job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    progress_pct = (job["processed"] / job["total"] * 100) if job["total"] > 0 else 0
    return JobStatus(job_id=job_id, progress_pct=progress_pct, **job)

@app.get("/jobs/{job_id}/results")
async def get_job_results(job_id: str):
    """Get partial or complete results for a batch job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "results": job.get("results", [])
    }
