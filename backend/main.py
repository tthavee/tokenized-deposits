"""
Tokenized Deposits — FastAPI backend entry point.

Start with:
    uvicorn main:app --reload
"""

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from typing import Any

import firebase_admin
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import credentials, firestore

from routers.admin import router as admin_router
from routers.clients import router as clients_router
from services.event_listener import run_event_listener

load_dotenv()


def _init_firebase() -> firestore.Client:
    cred_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS", "secrets/firebase-credentials.json"
    )
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    return firestore.client()


def _load_token_registry(db: firestore.Client) -> dict[str, Any]:
    registry: dict[str, Any] = {}
    docs = db.collection("token_registry").stream()
    for doc in docs:
        registry[doc.id] = doc.to_dict()
    print(f"[startup] loaded {len(registry)} token_registry entries: {list(registry.keys())}")
    return registry


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = _init_firebase()
    app.state.db = db
    app.state.token_registry = _load_token_registry(db)

    listener_task = asyncio.create_task(run_event_listener(app.state))
    yield
    listener_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await listener_task


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Tokenized Deposits API", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clients_router)
app.include_router(admin_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
