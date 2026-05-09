# gnafer

High-performance local Australian geocoder using GNAF CORE, Qwen2.5 (Ollama), and PostgreSQL.

## Quick Start

1. Copy `.env.example` to `.env` and fill in your details.
2. Run `make setup` to install dependencies.
3. Run `make start` to launch the database.
4. Run `make db-init` to load GNAF data.
5. Run `make db-status` to verify the ingestion.
6. Run `make run` to process addresses.

## Architecture

- **PostgreSQL 16**: Containerised database for GNAF CORE storage.
- **Ollama**: Local LLM (Qwen2.5) for complex address parsing (Host-based).
- **uv**: Deterministic Python dependency management.
