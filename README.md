# Planka Telegram Bot

Telegram bot with Python, aiogram, and Planka integration. Uses long-polling to receive updates.

## What you need

- Telegram bot token from @BotFather
- Planka URL + credentials
- PostgreSQL (for short-id mappings)
- Docker + Docker Compose plugin
- `make`

## 1) Configure env

Copy env file and fill values:

```bash
cp .env.example .env
```

Required: `BOT_TOKEN`, `DATABASE_URL`, `PLANKA_*`. For Planka action notifications to Telegram, set `TELEGRAM_NOTIFICATION_CHAT_IDS` and `PLANKA_BOARD_ID` (use `scripts/discover_chats.py` to find chat IDs).

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
uv run python -m app.polling
```

## Bot commands

- `/start` — greeting
- `/help` — list commands
- `/boards` — list Planka boards
- `/todo` — list TODO tasks
- `/todo {name}` — create a task (supports multi-line checklist items and photo attachments)
- `/task {id}` — show full task details (title, description, checklist, images)
- `/doing {id}` — move task to IN PROGRESS
- `/done {id}` — move task to DONE
- `/backtodo {id}` — move task back to TODO

## Notes

- Planka auth uses `PLANKA_USERNAME_OR_EMAIL` and `PLANKA_PASSWORD` (login on startup).
