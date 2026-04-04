"""
Seed Firestore with initial data for local development.

Usage:
    GOOGLE_APPLICATION_CREDENTIALS=secrets/firebase-credentials.json python scripts/seed_firestore.py
"""

import os
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, firestore

CREDENTIALS_PATH = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "secrets/firebase-credentials.json",
)

cred = credentials.Certificate(CREDENTIALS_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()


def seed_token_registry() -> None:
    doc_ref = db.collection("token_registry").document("USD_hardhat")
    doc_ref.set({
        "asset_type": "USD",
        "network": "hardhat",
        # Placeholder — update after deploying the DepositToken contract (issue #5/#6)
        "contract_address": "",
        "deployed_at": None,
        "deployer_address": "",
    })
    print("Seeded token_registry/USD_hardhat")


def seed_system() -> None:
    doc_ref = db.collection("system").document("event_listener")
    doc_ref.set({
        "last_processed_block": 0,
    })
    print("Seeded system/event_listener")


if __name__ == "__main__":
    seed_token_registry()
    seed_system()
    print("Done.")
