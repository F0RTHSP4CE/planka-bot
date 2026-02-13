.PHONY: up down logs restart ps build

DC := docker compose

up:
	$(DC) up -d --build

down:
	$(DC) down

logs:
	$(DC) logs -f bot

restart:
	$(DC) restart bot

ps:
	$(DC) ps

build:
	$(DC) build
