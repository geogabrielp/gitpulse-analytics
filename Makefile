.PHONY: \
	help up down restart logs ps reset \
	install \
	format lint typecheck rmcache \
	test test-cov \
	pipeline export-data dashboard

help:
	@echo
	@echo "Gitpulse Analytics Commands:"
	@echo ""
	@echo "[INFRASTRUCTURE]"
	@echo "   make up:       Start Docker Compose and set up MinIO buckets"
	@echo "   make down:     Stop the infrastructure"
	@echo "   make restart:  Restart the infrastructure"
	@echo "   make logs:     View the infrastructure logs"
	@echo "   make ps:       List running containers"
	@echo "   make reset:    Remove all data and volumes. WARNING: destructive!"
	@echo ""
	@echo "[APPLICATION]"
	@echo "   make install:  Install dependencies with uv"
	@echo ""
	@echo "[DEVELOPMENT]"
	@echo "   make format:    Format code with ruff"
	@echo "   make lint:      Check code with ruff"
	@echo "   make typecheck: Check types with ty"
	@echo "   make rmcache:   Remove __pycache__, .ruff_cache, .pytest_cache, and coverage artifacts"
	@echo ""
	@echo "[TESTING]"
	@echo "   make test:      Run all tests (fast-fail on first error)"
	@echo "   make test-cov:  Run all tests with coverage report"
	@echo ""
	@echo "[PIPELINE]"
	@echo "   make pipeline:    Run the full ETL pipeline (bronze + silver + gold)"
	@echo "   make export-data: Export MinIO data to static Parquet for dashboard"
	@echo "   make dashboard:   Launch the Streamlit dashboard"
	@echo

up:
	docker compose --env-file .env.example up -d --wait
	uv run python infra/scripts/init_minio.py

down:
	docker compose --env-file .env.example down

restart:
	docker compose --env-file .env.example down
	docker compose --env-file .env.example up -d

logs:
	docker compose --env-file .env.example logs -f

ps:
	docker compose --env-file .env.example ps

reset:
	docker compose --env-file .env.example down -v --remove-orphans
	docker system prune -f

install:
	uv sync

format:
	uv run ruff format .

lint:
	uv run ruff check .

typecheck:
	uv run ty check .

pipeline:
	uv run python main.py

export-data:
	uv run python scripts/export_dashboard_data.py

dashboard:
	uv run streamlit run dashboard/app.py

test:
	uv run pytest tests/ -x --verbose

test-cov:
	uv run pytest tests/ --cov=src --cov-report=term-missing

rmcache:
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@find . -type f -name ".coverage.*" -delete 2>/dev/null || true
	@echo "Cache cleaned!"
