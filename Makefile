.PHONY: help setup start stop status db-init db-status test run clean serve wait-db

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies using uv
	uv sync --all-extras

start: ## Start the database container
	docker compose up -d

stop: ## Stop the database container
	docker compose down

wait-db: ## Wait for the database to become healthy
	@echo "Waiting for database..."
	@until docker exec gnafer-db pg_isready -U postgres -d gnafer > /dev/null 2>&1; do \
		sleep 1; \
	done
	@echo "Database is ready."

status: ## Show status of all components
	@docker compose ps
	@echo "--- Ollama ---"
	@curl -sf http://localhost:11434/api/tags > /dev/null && echo "  Ollama: UP" || echo "  Ollama: DOWN"

db-init: wait-db ## Initialise the database schema and load GNAF data
	uv run python src/ingest.py

db-status: ## Show database ingestion status
	@echo "Database Row Count:"
	@docker exec -it gnafer-db psql -U postgres -d gnafer -c "SELECT count(*) FROM gnaf_core;"
	@echo "\nSample Data:"
	@docker exec -it gnafer-db psql -U postgres -d gnafer -c "SELECT address_detail_pid, street_name, suburb_name, postcode FROM gnaf_core LIMIT 2;"

test: ## Run unit tests
	uv run pytest tests/ -v --tb=short

run: wait-db ## Run the geocoding pipeline
	uv run python src/main.py

serve: wait-db ## Launch the FastAPI server
	uv run uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

clean: ## Clean up temporary files
	rm -rf __pycache__ src/__pycache__ tests/__pycache__
	rm -f geocoded.csv
