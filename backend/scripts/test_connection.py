"""
Verify Firestore connectivity with a simple read/write test.

Usage:
    GOOGLE_APPLICATION_CREDENTIALS=secrets/firebase-credentials.json python scripts/test_connection.py
"""

import os
import firebase_admin
from firebase_admin import credentials, firestore

CREDENTIALS_PATH = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "secrets/firebase-credentials.json",
)

cred = credentials.Certificate(CREDENTIALS_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()


def test_write_read_delete() -> None:
    ref = db.collection("system").document("_connection_test")

    ref.set({"ok": True})
    print("Write: OK")

    doc = ref.get()
    assert doc.exists and doc.to_dict() == {"ok": True}, "Read mismatch"
    print("Read:  OK")

    ref.delete()
    assert not ref.get().exists, "Delete failed"
    print("Delete: OK")


def test_seed_documents() -> None:
    token = db.collection("token_registry").document("USD_hardhat").get()
    system = db.collection("system").document("event_listener").get()

    print(f"token_registry/USD_hardhat exists: {token.exists}")
    print(f"system/event_listener exists:      {system.exists}")

    if system.exists:
        data = system.to_dict()
        assert "last_processed_block" in data, "Missing last_processed_block field"
        print(f"  last_processed_block: {data['last_processed_block']}")


if __name__ == "__main__":
    print("--- Connection test ---")
    test_write_read_delete()
    print("\n--- Seed document check ---")
    test_seed_documents()
    print("\nAll checks passed.")
