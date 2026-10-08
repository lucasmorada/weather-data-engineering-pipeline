.PHONY: help install test run run-local up init-airflow down logs clean

PYTHON ?= python

help:
	@echo "Available commands:"
	@echo "  make install       install Python dependencies"
	@echo "  make test          run the unit tests"
	@echo "  make run-local     extract, transform and validate (no database)"
	@echo "  make run           full pipeline including PostgreSQL"
	@echo "  make init-airflow  one-time Airflow setup (Docker)"
	@echo "  make up            start PostgreSQL and Airflow (Docker)"
	@echo "  make down          stop the containers"
	@echo "  make logs          follow container logs"
	@echo "  make clean         remove caches and generated data"

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest -v

run-local:
	$(PYTHON) -m src.pipeline --skip-db

run:
	$(PYTHON) -m src.pipeline

init-airflow:
	docker compose up airflow-init

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache
	find data/raw data/processed -type f ! -name ".gitkeep" -delete
