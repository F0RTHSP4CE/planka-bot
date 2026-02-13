# Planka Telegram Bot

Simple Telegram bot with Python, FastAPI, aiogram, and Planka integration.

## What you need

- Telegram bot token from @BotFather
- Planka URL + credentials
- Docker + Docker Compose plugin
- `make`

## 1) Configure env

Copy env file and fill values:

```bash
cp .env.example .env
```

## 2) Deploy on server (simple)

```bash
sudo make up
```

Useful commands:

```bash
sudo make ps
sudo make logs
sudo make restart
sudo make down
```

## 3) Local dev without Docker (optional)

```bash
uv sync
uv run uvicorn app.main:app --app-dir src --host 0.0.0.0 --port 8000 --reload
```

### Local Telegram testing without ngrok (polling mode)

Use this when you want to test commands from Telegram locally and do not want webhooks:

```bash
uv run python -m app.polling
```

Notes:
- Keep only one bot process running (webhook server or polling, not both).

## Bot commands

- `/start` — greeting
- `/help` — list commands
- `/boards` — list Planka boards
- `/todo` — list TODO tasks
- `/todo {name}` — create a task (supports multi-line checklist items and photo attachments)
- `/doing {id}` — move task to IN PROGRESS
- `/done {id}` — move task to DONE

## Notes

- Planka auth uses `PLANKA_USERNAME_OR_EMAIL` and `PLANKA_PASSWORD` (login on startup).
