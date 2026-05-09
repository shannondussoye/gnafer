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

# In-memory job store (In production, use Redis/DB)
jobs = {}

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "database": "connected"}

@app.post("/geocode", response_model=GeocodedResult)
async def geocode_single(request: GeocodeRequest):
    """Geocode a single address using the high-performance waterfall."""
    addr = request.address
    
    # 1. Regex Pass
    parsed = parse_address_simple(addr)
    if parsed:
        match = matcher.match(parsed)
        if match:
            match.parse_method = "REGEX"
            return match
            
    # 2. LLM Pass (Async)
    parsed = await parse_address_llm_async(addr)
    if parsed:
        match = matcher.match(parsed)
        if match:
            match.parse_method = "LLM"
            return match
            
    # 3. Failure
    raise HTTPException(status_code=404, detail=f"Could not geocode address: {addr}")

async def process_batch_job(job_id: str, addresses: List[str]):
    """Background worker for batch geocoding."""
    results = []
    pending_llm = []
    
    # --- Pass 1: Regex ---
    for addr in addresses:
        parsed = parse_address_simple(addr)
        if parsed:
            match = matcher.match(parsed)
            if match:
                match.parse_method = "REGEX"
                results.append(match)
                jobs[job_id]["processed"] += 1
                jobs[job_id]["successful"] += 1
                continue
        pending_llm.append(addr)
        jobs[job_id]["processed"] += 1

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
                    results.append(match)
                    jobs[job_id]["successful"] += 1
            # We don't increment "processed" here because we did it in Pass 1

    jobs[job_id]["status"] = "completed"
    jobs[job_id]["results"] = [r.model_dump() for r in results]

@app.post("/geocode/batch")
async def geocode_batch(request: BatchGeocodeRequest, background_tasks: BackgroundTasks):
    """Start a batch geocoding job in the background."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "processing",
        "total": len(request.addresses),
        "processed": 0,
        "successful": 0
    }
    
    background_tasks.add_task(process_batch_job, job_id, request.addresses)
    
    return {"job_id": job_id, "message": "Batch job started"}

@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Check the status of a background job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    return JobStatus(job_id=job_id, **job)
