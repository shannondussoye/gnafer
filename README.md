# gnafer

High-performance local Australian geocoder using GNAF CORE, Qwen2.5 (Ollama), and PostgreSQL.

## Features

- **27-Field GNAF Mapping**: Full fidelity ingestion of the GNAF CORE dataset (15.8M rows).
- **Two-Pass Pipeline**: High-performance batch processing optimized for 100k+ rows.
    - **Pass 1 (Regex Sprint)**: Instant geocoding for standard addresses (~2,500 rows/sec).
    - **Pass 2 (Async LLM)**: 9x faster refinement using `qwen2.5:1.5b` and concurrent `asyncio` batches.
- **Precision Matcher**: Type-aware hierarchical search (Unit -> Number -> Street).
- **Observability**: Built-in support for Logtail (Recorder) and Healthchecks.io (Pulse).

## API Usage

Launch the API server with `make serve`.

### Single Geocode
```bash
curl -X POST http://localhost:8000/geocode \
     -H "Content-Type: application/json" \
     -d '{"address": "1 George Street, Sydney"}'
```

### Batch Geocode
```bash
curl -X POST http://localhost:8000/geocode/batch \
     -H "Content-Type: application/json" \
     -d '{"addresses": ["1 George St, Sydney", "497 New South Head Rd, Double Bay"]}'
```
Check status: `curl http://localhost:8000/jobs/{job_id}`

## Performance

| Model | Mode | Speed |
| :--- | :--- | :--- |
| Regex Only | Synchronous | ~2,500 it/s |
| Qwen 7B | Synchronous | ~10s / address |
| **Qwen 1.5B** | **Asynchronous** | **~1.1s / address** |

## Architecture

- **PostgreSQL 16**: Containerised database with `pg_trgm` for fuzzy matching.
- **Ollama**: Local LLM for complex parsing (Host-based to leverage GPU).
- **Two-Pass Pipeline**: 
    1. **Stage 1 (Regex)**: Instant, rule-based parsing.
    2. **Stage 2 (LLM)**: Intelligent fallback for ambiguous addresses.
- **uv**: Deterministic Python dependency management.
