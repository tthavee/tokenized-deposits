"""
Tokenized Deposits — FastAPI backend entry point.

Start with:
    uvicorn main:app --reload
"""

import os
from contextlib import asynccontextmanager
from typing import Any

import firebase_admin
from dotenv import load_dotenv
from fastapi import FastAPI
from firebase_admin import credentials, firestore

load_dotenv()

# ---------------------------------------------------------------------------
# In-memory token registry  {asset_type}_{network} -> registry document dict
# ---------------------------------------------------------------------------
token_registry: dict[str, dict[str, Any]] = {}


def _init_firebase() -> firestore.Client:
    cred_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS", "secrets/firebase-credentials.json"
    )
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    return firestore.client()


def _load_token_registry(db: firestore.Client) -> None:
    docs = db.collection("token_registry").stream()
    for doc in docs:
        token_registry[doc.id] = doc.to_dict()
    print(f"[startup] loaded {len(token_registry)} token_registry entries: {list(token_registry.keys())}")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = _init_firebase()
    _load_token_registry(db)
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Tokenized Deposits API", lifespan=lifespan)


@app.get("/health")
def health_check():
    return {"status": "ok"}
