"""
Standalone event listener — run this separately from the FastAPI backend.

Usage:
    cd backend
    venv/bin/python scripts/run_event_listener.py

Stop with Ctrl+C.
"""

import asyncio
import logging
import os
import sys

# Allow imports from the backend root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import firebase_admin
from firebase_admin import credentials, firestore

from services.event_listener import run_event_listener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def _init() -> object:
    cred_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS", "secrets/firebase-credentials.json"
    )
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    # Load token registry so the listener has something to work with immediately.
    token_registry = {
        doc.id: doc.to_dict()
        for doc in db.collection("token_registry").stream()
    }
    print(f"[startup] loaded {len(token_registry)} token_registry entries: {list(token_registry.keys())}")

    class _State:
        pass

    state = _State()
    state.db = db
    state.token_registry = token_registry
    return state


async def main() -> None:
    state = _init()
    await run_event_listener(state)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[event_listener] stopped")
