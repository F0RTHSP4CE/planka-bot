#!/usr/bin/env -S uv run python
"""
Discover Telegram chat IDs and topic (thread) IDs, then send a test message.
Run this script. Stop any running bot instance first (webhook/polling) to allow getUpdates.
Pass --todo-thread ID and --plan-logs-thread ID if you know them (e.g. from topic URL).
"""
import argparse
import asyncio
import os
import sys

# Add src to path for app imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    print("BOT_TOKEN not set in .env")
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Discover chat IDs and send meooow")
    p.add_argument("--todo-thread", type=int, help="Topic/thread ID for TODO in @F0_PUBLIC_CHAT")
    p.add_argument("--plan-logs-thread", type=int, help="Topic/thread ID for plan logs in notify chat")
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # 1. Get @F0_PUBLIC_CHAT chat ID
    print("Fetching @F0_PUBLIC_CHAT...")
    try:
        chat = await bot.get_chat("@F0_PUBLIC_CHAT")
        public_chat_id = chat.id
        print(f"  -> Chat ID: {public_chat_id}")
    except Exception as e:
        print(f"  -> Error: {e}")
        public_chat_id = None

    # 2. Get recent updates to discover topic (thread) IDs (optional)
    todo_thread_id: int | None = args.todo_thread
    notify_chat_id: int | None = 2070662990
    plan_logs_thread_id: int | None = args.plan_logs_thread

    if todo_thread_id is None or plan_logs_thread_id is None:
        print("\nAttempting to fetch updates (stop any running bot first)...")
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            updates = await bot.get_updates(limit=100, timeout=20)
            seen: dict[int, set[int | None]] = {}
            for u in updates:
                msg = u.message or u.edited_message
                if not msg or not msg.chat:
                    continue
                cid = msg.chat.id
                tid = getattr(msg, "message_thread_id", None)
                if cid not in seen:
                    seen[cid] = set()
                seen[cid].add(tid)
                title = getattr(msg.chat, "title", None) or str(cid)
                thread_info = f" (thread_id={tid})" if tid else ""
                print(f"  -> {title}: chat_id={cid}{thread_info}")

            if public_chat_id and public_chat_id in seen and todo_thread_id is None:
                threads = [t for t in seen[public_chat_id] if t is not None]
                if threads:
                    todo_thread_id = threads[0]
            if 2070662990 in seen and plan_logs_thread_id is None:
                threads = [t for t in seen[2070662990] if t is not None]
                if threads:
                    plan_logs_thread_id = threads[0]
        except TelegramConflictError:
            print("  -> Conflict: another bot instance is running. Use --todo-thread and --plan-logs-thread.")

    # 4. Send meooow to both
    targets: list[tuple[int, int | None, str]] = []
    if public_chat_id:
        targets.append((public_chat_id, todo_thread_id, "F0_PUBLIC_CHAT TODO"))
    if notify_chat_id:
        targets.append((notify_chat_id, plan_logs_thread_id, "notify plan logs"))

    if not targets:
        print("\nNo targets to send to. Add chat IDs manually or send messages in topics and re-run.")
        await bot.session.close()
        return

    print("\nSending 'meooow' to:")
    for chat_id, thread_id, label in targets:
        try:
            kwargs: dict = {"chat_id": chat_id, "text": "meooow"}
            if thread_id is not None:
                kwargs["message_thread_id"] = thread_id
            await bot.send_message(**kwargs)
            tid_str = f":{thread_id}" if thread_id else ""
            print(f"  -> {label}: {chat_id}{tid_str} ✓")
        except Exception as e:
            print(f"  -> {label}: {chat_id} ✗ {e}")

    # 5. Print env format
    print("\n--- Add to .env ---")
    for chat_id, thread_id, _ in targets:
        if thread_id is not None:
            print(f"# Format: chat_id:thread_id for topic")
            print(f"TELEGRAM_CHAT_{chat_id}={chat_id}:{thread_id}")
        else:
            print(f"TELEGRAM_CHAT_{chat_id}={chat_id}")

    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
