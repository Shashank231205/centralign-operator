.PHONY: up down install browsers migrate seed api worker sandbox frontend lint format typecheck test test-integration test-e2e

up:            ## start the whole stack in containers
	docker compose up -d --build

down:
	docker compose down

install:       ## local dev install (Python workspace + frontend)
	uv sync
	uv run poe browsers
	cd frontend && npm ci

browsers:
	uv run poe browsers

migrate:
	uv run poe migrate

seed:
	uv run poe seed

api:
	uv run poe api

worker:
	uv run poe worker

sandbox:
	uv run poe sandbox-portal & uv run poe sandbox-erp

frontend:
	cd frontend && npm run dev

lint:
	uv run poe lint
	cd frontend && npm run lint

format:
	uv run poe format

typecheck:
	uv run poe typecheck
	cd frontend && npm run typecheck

test:
	uv run poe test

test-integration:
	uv run poe test-integration

test-e2e:
	uv run poe test-e2e
