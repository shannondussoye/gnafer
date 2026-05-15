# 📍 gnafer — TODO & Implementation Plan

## Overview

This file tracks prioritised improvements across infrastructure hardening, API features, and design principle compliance for the GNAF CORE geocoder.

---

## 🟠 Priority 2 — API & Data Quality

### 2.1 Add Fuzzy Match Confidence Scoring

**Problem:** The geocoder returns matches via trigram similarity but doesn't expose a confidence score to the caller. Consumers can't distinguish between a high-confidence exact match and a low-confidence fuzzy guess.

**Implementation Plan:**
1. Return the trigram similarity score alongside the matched address in the API response
2. Add a `min_confidence` query parameter to filter low-quality matches
3. Log match confidence in Logtail for analytics on geocoding quality

---

### 2.2 Add Batch Geocoding Progress Endpoint

**Problem:** The batch geocoding endpoint returns results asynchronously but provides no way for the caller to check progress on large batches.

**Implementation Plan:**
1. Store batch job status in-memory (or Redis if needed later)
2. Add `GET /batch/{job_id}/status` endpoint returning progress percentage and partial results
3. Add a TTL to clean up completed job results after 1 hour

---

## 🟡 Priority 3 — Infrastructure & Observability

### 3.1 Add Healthchecks.io Integration

**Problem:** The geocoder has Logtail for debugging but no crash alerting. If the FastAPI process dies silently, there is no notification.

**Implementation Plan:**
1. Add a Healthchecks.io UUID to `.env` and `.env.example`
2. Ping the UUID at the end of each successful geocoding batch (or on a periodic heartbeat)
3. Configure Healthchecks.io to alert on missed pings

---

### 3.2 Add Resource Limits to `db` Service

**Problem:** The `docker-compose.yml` database service has no `cpus` or `mem_limit` set. A runaway PostgreSQL query could starve the host.

**Implementation Plan:**
1. Add resource limits to the `db` service in `docker-compose.yml`:
   ```yaml
   mem_limit: 2G
   cpus: 1.0
   ```
2. Monitor with `docker stats` under load to validate the limits are appropriate

---

### 3.3 Add Docker Log Rotation

**Problem:** The `db` service runs with `restart: always` but has no log rotation configured. Docker's default logging will grow unbounded.

**Implementation Plan:**
1. Add to the `db` service in `docker-compose.yml`:
   ```yaml
   logging:
     driver: "json-file"
     options:
       max-size: "50m"
       max-file: "3"
   ```

---

## 🟢 Priority 4 — Developer Experience

### 4.1 Add Standard `status` Target to Makefile

**Problem:** The Makefile has a `db-status` target but not the standard `status` target required by §2.10.

**Implementation Plan:**
1. Add a `status` target that shows both the database container status and the host-native service health:
   ```makefile
   status: ## Show status of all components
   	docker compose ps
   	@echo "--- Ollama ---"
   	@curl -sf http://localhost:11434/api/tags > /dev/null && echo "  Ollama: UP" || echo "  Ollama: DOWN"
   ```

---

### 4.2 Add `env_file` to Docker Compose

**Problem:** The `docker-compose.yml` uses inline `environment:` blocks with `${VAR:-default}` syntax instead of `env_file: .env`.

**Implementation Plan:**
1. Add `env_file: .env` to the `db` service
2. Move the `POSTGRES_*` variables to `.env` and `.env.example`
3. Keep `${VAR:-default}` syntax only where environment-specific overrides are needed

---

### 4.3 Write Unit Tests

**Problem:** No automated tests exist. The regex parser, LLM normalizer, and geocoding logic have no test coverage.

**Implementation Plan:**
1. Create `tests/` directory at project root
2. Start with pure-logic functions:
   - `tests/test_regex_parser.py` — test address parsing with known inputs
   - `tests/test_geocoder.py` — test trigram matching with mock database
3. Add `pytest` to `pyproject.toml` dev dependencies
4. Add a `make test` target: `uv run pytest tests/ -v`

---

## ✅ Completion Checklist

- [x] 2.1 Add fuzzy match confidence scoring to API response
- [x] 2.2 Add batch geocoding progress endpoint
- [ ] 3.1 Integrate Healthchecks.io heartbeat
- [x] 3.2 Add resource limits to `db` service in compose
- [x] 3.3 Add Docker log rotation to `db` service
- [x] 4.1 Add standard `status` target to Makefile
- [x] 4.2 Add `env_file` to Docker Compose
- [ ] 4.3 Write unit tests with `pytest`

### GEMINI.md Compliance Gaps
*Sourced from [PORTFOLIO.md](file:///home/shannon/Workspace/projects/PORTFOLIO.md) §3 compliance matrix.*

- [x] **§2.2** Add resource limits (`cpus`, `mem_limit`) to `db` service *(covered by 3.2)*
- [x] **§2.3** Migrate `docker-compose.yml` to use `env_file: .env` *(covered by 4.2)*
- [x] **§2.10** Add standard `status` Makefile target *(covered by 4.1)*
- [ ] **§2.11** Integrate Healthchecks.io heartbeat *(covered by 3.1)*
- [ ] **§2.11** Wire up ntfy alerting via Healthchecks.io notification settings
- [x] **§2.12** Add Docker log rotation (`json-file` driver with `max-size`/`max-file`) *(covered by 3.3)*
- [ ] **§2.13** Add `tests/` directory with `pytest` test suite *(covered by 4.3)*
