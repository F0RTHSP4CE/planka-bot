#!/usr/bin/env python3
"""Fetch Planka board actions and inspect structure, especially for delete/move-to-trash."""

import asyncio
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("PLANKA_BASE_URL", "").rstrip("/")
USER = os.environ.get("PLANKA_USERNAME_OR_EMAIL")
PASS = os.environ.get("PLANKA_PASSWORD")
BOARD_ID = os.environ.get("PLANKA_BOARD_ID")

if not BASE_URL or not USER or not PASS or not BOARD_ID:
    print("PLANKA_BASE_URL, PLANKA_USERNAME_OR_EMAIL, PLANKA_PASSWORD, and PLANKA_BOARD_ID must be set")
    sys.exit(1)


async def main() -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Login
        r = await client.post(
            f"{BASE_URL}/api/access-tokens",
            json={"emailOrUsername": USER, "password": PASS},
        )
        r.raise_for_status()
        token = r.json().get("item")
        if not token:
            print("Login failed: no token")
            return
        client.headers["Authorization"] = f"Bearer {token}"

        # Fetch board actions
        r = await client.get(f"{BASE_URL}/api/boards/{BOARD_ID}/actions")
        r.raise_for_status()
        data = r.json()
        items = data.get("items") or []

        print(f"Found {len(items)} actions\n")
        print("=" * 60)

        for i, action in enumerate(items[:15]):
            atype = action.get("type")
            data_obj = action.get("data") or {}
            from_list = data_obj.get("fromList") or {}
            to_list = data_obj.get("toList") or data_obj.get("list") or {}
            card = data_obj.get("card") or {}

            print(f"\n--- Action {i+1}: {atype} (id={action.get('id')}) ---")
            print(f"  cardId: {action.get('cardId')}")
            print(f"  card.name: {card.get('name')}")
            print(f"  fromList: {json.dumps(from_list, indent=4)}")
            print(f"  toList: {json.dumps(to_list, indent=4)}")

            if atype == "moveCard":
                to_name = (to_list or {}).get("name")
                to_type = (to_list or {}).get("type")
                print(f"  -> toList.name: {repr(to_name)}, toList.type: {repr(to_type)}")


if __name__ == "__main__":
    asyncio.run(main())
