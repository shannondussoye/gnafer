.PHONY: help setup start stop db-init db-status test run clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies using uv
	uv sync

start: ## Start the database container
	docker-compose up -d

stop: ## Stop the database container
	docker-compose down

db-init: ## Initialise the database schema and load GNAF data
	uv run python src/ingest.py

db-status: ## Show database ingestion status
	@echo "Database Row Count:"
	@docker exec -it gnafer-db psql -U postgres -d gnafer -c "SELECT count(*) FROM gnaf_core;"
	@echo "\nSample Data:"
	@docker exec -it gnafer-db psql -U postgres -d gnafer -c "SELECT address_detail_pid, street_name, suburb_name, postcode FROM gnaf_core LIMIT 2;"

test: ## Run unit tests
	uv run pytest tests/

run: ## Run the geocoding pipeline
	uv run python src/main.py

serve: ## Launch the FastAPI server
	uv run uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

clean: ## Clean up temporary files
	rm -rf __pycache__ src/__pycache__ tests/__pycache__
	rm -f geocoded.csv
