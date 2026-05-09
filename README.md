# gnafer

High-performance local Australian geocoder using GNAF CORE, Qwen2.5 (Ollama), and PostgreSQL.

## Quick Start

1. Copy `.env.example` to `.env` and fill in your details.
2. Run `make setup` to install dependencies.
3. Run `make start` to launch the database.
4. Run `make db-init` to load GNAF data.
5. Run `make run` to process addresses.
