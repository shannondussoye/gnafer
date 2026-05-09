# gnafer

High-performance local Australian geocoder using GNAF CORE, Qwen2.5 (Ollama), and PostgreSQL.

## Quick Start

1. Copy `.env.example` to `.env` and fill in your details.
2. Run `make setup` to install dependencies.
3. Run `make start` to launch the database.
4. Run `make db-init` to load GNAF data.
5. Run `make db-status` to verify the ingestion.
6. Run `make run` to process addresses.

## Configuration

The project is configured via environment variables in the `.env` file:

- **OLLAMA_MODEL**: The model used for complex address parsing (default: `qwen2.5:latest`). You can switch to `deepseek-r1:7b` or others depending on your host setup.
- **OLLAMA_HOST**: The address of your Ollama server (default: `http://localhost:11434`).
- **DB_***: PostgreSQL connection details.

## Architecture

- **PostgreSQL 16**: Containerised database for GNAF CORE storage.
- **Ollama**: Local LLM for complex address parsing (Host-based to leverage ROCm/CUDA).
- **Waterfall Parser**: 
    1. **Stage 1 (Regex)**: Fast, rule-based parsing for standard addresses.
    2. **Stage 2 (LLM)**: High-fidelity fallback for ambiguous or messy addresses.
- **uv**: Deterministic Python dependency management.
