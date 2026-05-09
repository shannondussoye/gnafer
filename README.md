# GNAFER: High-Performance Australian Geocoder

GNAFER is a production-grade, local-first geocoding pipeline designed for high-precision Australian address resolution. It leverages the full **GNAF CORE** dataset (15.8M rows) combined with a hybrid **Two-Pass matching engine** (Regex + LLM) to achieve sub-unit accuracy at scale.

---

## 🚀 Key Features

- **Sub-Unit Precision**: Hierarchical matching logic that resolves down to Unit/Shop/Level (e.g., "Unit 5, Level 2...").
- **Mesh Block (mb_code) Support**: Returns the ABS Mesh Block code for every successful match, enabling direct linkage to Census data.
- **Two-Pass Hybrid Engine**:
    - **Pass 1 (Regex Sprint)**: Instant, rule-based geocoding for 80%+ of standard addresses (~2,500 rows/sec).
    - **Pass 2 (Async LLM Refinement)**: Concurrent AI refinement using `qwen2.5:1.5b` for complex or messy addresses.
- **FastAPI Microservice**: Integrated REST API with single and background-batch endpoints.
- **Cloud Observability**: Integrated "Recorder" pattern using **Logtail** for remote progress tracking.
- **Type-Aware Matching**: Intelligent handling of 50+ Australian street types and abbreviations (e.g., "Pde", "Cct", "St").

---

## 🛠️ Tech Stack

- **Logic**: Python 3.12+ (FastAPI, Pydantic, Asyncio)
- **Database**: PostgreSQL 16 + `pg_trgm` (Fuzzy Matching)
- **AI/LLM**: Ollama (`qwen2.5:1.5b`)
- **Package Manager**: `uv` (Deterministic dependencies)
- **Containerization**: Docker & Docker Compose

---

## 📦 Setup & Installation

### 1. Prerequisites
- Docker & Docker Compose
- [Ollama](https://ollama.com/) (Running on the host for GPU acceleration)
- Python 3.12+

### 2. Infrastructure
```bash
# Install dependencies
make setup

# Start the PostgreSQL container
make start

# Pull the required LLM model
ollama pull qwen2.5:1.5b
```

### 3. Data Ingestion
Place your `GNAF_CORE.psv` file in the `data/` directory and run:
```bash
make db-init
```
*Note: This processes ~15.8 million rows. Use `make db-status` to monitor progress.*

---

## 🖥️ Usage

### REST API (Recommended for Microservices)
Launch the server:
```bash
make serve
```

#### Single Address Geocode
**POST** `/geocode`
```bash
curl -X POST http://localhost:8000/geocode \
     -H "Content-Type: application/json" \
     -d '{"address": "42/7 Weston St, Rosehill 2142"}'
```

#### Batch Job (Background)
**POST** `/geocode/batch`
```bash
curl -X POST http://localhost:8000/geocode/batch \
     -H "Content-Type: application/json" \
     -d '{"addresses": ["1 George St, Sydney", "497 New South Head Rd, Double Bay"]}'
```
*Returns a `job_id`. Monitor status via `GET /jobs/{job_id}`.*

### CLI Batch Processing
For large file-based workloads:
```bash
make run
```
*Processes `input.txt` and generates `geocoded.csv`.*

---

## 📊 Performance Benchmarks

| Component | Speed | Optimization |
| :--- | :--- | :--- |
| **Database Match** | < 5ms / query | Indexed Hierarchical Search |
| **Regex Pass** | ~2,500 addresses/sec | Rule-based Sprint |
| **LLM Refinement** | ~1.1s / address | Async Concurrency (15x) |
| **Total Pipeline** | **9x Faster** | Transitioned from 7B to 1.5B Model |

---

## 📋 Environment Configuration (`.env`)

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DB_NAME` | PostgreSQL Database Name | `gnafer` |
| `OLLAMA_MODEL` | AI Model for Refinement | `qwen2.5:1.5b` |
| `LOGTAIL_TOKEN` | Remote Logging Token | (Optional) |

---

## 🛡️ License
MIT License. Created for high-performance Australian spatial data workloads.
