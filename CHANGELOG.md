# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed
- **Replaced matching engine** — Switched from regex parsing + exact SQL matching to trigram similarity matching with structural re-scoring
- **LLM role changed** — LLM now verifies near-matches (yes/no) instead of parsing addresses
- **Single data model** — Merged `ParsedAddress` + `GeocodedResult` into unified `MatchResult`
- **Removed pandas from pipeline** — CLI output now uses `csv.DictWriter` (pandas retained for ingestion only)
- **Connection pooling** — Shared `ThreadedConnectionPool` for API and batch processing

### Added
- `src/trigram_matcher.py` — Three-stage trigram matcher (`TrigramAddressMatcher` class)
- `src/llm_verifier.py` — LLM-based address verification module
- GitHub Actions CI workflow (pytest on push)
- `GREATEST()` SQL clause to handle `address_site_name`/`building_name` prefixes
- Configurable LLM verification threshold via `LLM_VERIFY_THRESHOLD`

### Removed
- `src/matcher.py` — Old exact-match `AddressMatcher`
- `src/simple_parser.py` — Regex address parser
- `src/llm_parser.py` — LLM address parser
- `src/parser.py` — Waterfall parser orchestrator

## [0.1.0] - 2026-05-25

### Added
- Initial release
- Two-pass geocoding pipeline (Regex + LLM parsing)
- FastAPI REST API with single and batch endpoints
- PostgreSQL + pg_trgm fuzzy matching
- Logtail + Healthchecks.io observability
- Docker Compose for PostgreSQL
- Makefile with self-documenting help
