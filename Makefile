.PHONY: install install-model setup-model install-web start dev-api dev-web migrate create-owner test check build-web compose-up compose-down compose-test purge-expired-exports example-xlsx

ifneq (,$(wildcard .env))
include .env
export
endif

install:
	uv sync --locked --extra test

install-model:
	uv sync --locked --extra model --extra test

setup-model:
	python3 -m scripts.setup_model

install-web:
	cd apps/web && npm ci --no-audit --no-fund

start: build-web
	uv run --locked --extra model --extra test python -m scripts.run_local

dev-api:
	uv run --locked python -m uvicorn apps.api.asdos_api.main:app --host 127.0.0.1 --port 8000 --reload

dev-web:
	cd apps/web && ASDOS_API_URL=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1

migrate:
	uv run --locked python -m alembic upgrade head

create-owner:
	uv run --locked python -m scripts.create_owner

test:
	uv run --locked python -m pytest -q

check:
	uv run --locked python -m compileall -q apps packages migrations scripts tests

build-web:
	cd apps/web && npm run build

compose-up:
	docker compose --env-file .env -f deploy/compose.yaml up --build -d

compose-down:
	docker compose --env-file .env -f deploy/compose.yaml down

compose-test:
	bash scripts/run_compose_e2e.sh

purge-expired-exports:
	uv run --locked python -m scripts.purge_expired_exports $(ARGS)

example-xlsx:
	uv run --locked python -m scripts.build_example_export
