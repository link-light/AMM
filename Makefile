# AI Money Machine - Makefile

.PHONY: help setup up down logs migrate seed test test-e2e dev prod clean

help: ## Show this help message
	@echo "AI Money Machine - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and initialize database
	@echo "Setting up AMM..."
	pip install -r requirements.txt
	cd dashboard && npm install
	cp .env.example .env
	@echo "Setup complete! Edit .env with your configuration."

up: ## Start Docker services (Redis, PostgreSQL)
	docker-compose up -d
	@echo "Services started. Waiting for health checks..."
	@sleep 5
	@echo "Ready!"

down: ## Stop Docker services
	docker-compose down

logs: ## View service logs
	docker-compose logs -f

migrate: ## Run database migrations
	alembic upgrade head

seed: ## Import seed data
	cd scripts && python seed_data.py

test: ## Run unit tests
	pytest tests/ -v --tb=short

test-e2e: ## Run end-to-end tests
	cd scripts && python test_e2e.py

dev: ## Start development mode (Mock mode)
	@echo "Starting AMM in development mode..."
	@echo "API: http://localhost:8000"
	@echo "Dashboard: http://localhost:3000"
	$(MAKE) up
	@sleep 3
	$(MAKE) migrate
	$(MAKE) seed
	@echo "Starting API server..."
	python main.py api &
	@sleep 2
	@echo "Starting dashboard..."
	cd dashboard && npm run dev

prod: ## Start production mode
	@echo "Starting AMM in production mode..."
	docker-compose -f docker-compose.yml up -d

worker: ## Start Celery workers
	celery -A celery_app worker --loglevel=info

beat: ## Start Celery beat (scheduler)
	celery -A celery_app beat --loglevel=info

clean: ## Clean up Docker containers and volumes
	docker-compose down -v
	rm -rf logs/*.log

lint: ## Run linting
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	black . --check

format: ## Format code
	black .

# Development shortcuts
dev-api: ## Start only API server
	python main.py api

dev-worker: ## Start only worker
	python main.py worker

dev-evaluator: ## Start only evaluator
	python main.py evaluator

dev-scout: ## Run scout once
	python -c "import asyncio; from scouts.freelance_scout import FreelanceScout; asyncio.run(FreelanceScout().run_once())"
