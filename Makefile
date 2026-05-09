.PHONY: help setup start stop status logs db-init db-index run test

# Default target: help
help:
	@echo "gnafer - High-Performance Local Geocoder"
	@echo ""
	@echo "Usage:"
	@echo "  make setup      - Install dependencies using uv"
	@echo "  make start      - Start database service"
	@echo "  make stop       - Stop database service"
	@echo "  make status     - Check service status"
	@echo "  make logs       - Tail service logs"
	@echo "  make db-init    - Initialise database schema and load sample data"
	@echo "  make db-index   - Apply performance indexes to the database"
	@echo "  make db-status  - Check database row counts and sample data"
	@echo "  make run        - Execute the geocoding pipeline"
	@echo "  make test       - Run pytest suite"
	@echo ""

setup:
	@echo "Setting up environment..."
	uv sync

start:
	@echo "Starting services..."
	docker compose up -d
	@echo "Waiting for database to be ready..."
	@until docker compose exec db pg_isready -U postgres > /dev/null 2>&1; do \
		echo "Waiting..."; \
		sleep 2; \
	done
	@echo "Database is ready."

stop:
	@echo "Stopping services..."
	docker compose down

status:
	@docker compose ps

logs:
	@docker compose logs -f

db-init:
	@echo "Initialising database..."
	uv run python src/ingest.py

db-status:
	@echo "Database Row Count:"
	@docker compose exec db psql -U postgres -d gnafer -t -c "SELECT count(*) FROM gnaf_core;"
	@echo "\nSample Data:"
	@docker compose exec db psql -U postgres -d gnafer -c "SELECT address_detail_pid, street_name, suburb_name, postcode FROM gnaf_core LIMIT 5;"

run:
	@echo "Running geocoding pipeline..."
	uv run python src/main.py

test:
	@echo "Running tests..."
	uv run pytest tests/
