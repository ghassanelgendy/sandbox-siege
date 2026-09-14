.PHONY: up down logs reset install dev api web doctor test seed clean

up:            ## Start LocalStack Pro sandbox + SearXNG
	docker compose up -d
	@echo "Waiting for LocalStack..."
	@until curl -sf http://localhost:4566/_localstack/health >/dev/null 2>&1; do sleep 1; done
	@echo "LocalStack ready."
	@echo "Waiting for SearXNG (web_search backend)..."
	@until curl -sf "http://localhost:18080/search?q=ping&format=json" >/dev/null 2>&1; do sleep 1; done
	@echo "SearXNG ready (JSON API)."

down:
	docker compose down

logs:
	docker compose logs -f localstack

reset:         ## Wipe sandbox state without restarting
	curl -sf -X POST http://localhost:4566/_localstack/state/reset && echo "state reset"

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -q -e ".[dev]"
	cd frontend && npm install

api:           ## Run backend API
	cd backend && .venv/bin/uvicorn siege.main:app --reload --port 8000

web:           ## Run frontend dev server
	cd frontend && npm run dev

dev:           ## Run both
	@$(MAKE) -j2 api web

doctor:
	cd backend && .venv/bin/siege doctor

test:
	cd backend && .venv/bin/pytest -q

seed:          ## Populate leaderboard runs
	cd backend && .venv/bin/siege seed

clean:
	rm -rf backend/.venv frontend/node_modules .localstack-data
