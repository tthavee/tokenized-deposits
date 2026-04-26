"""
Migration script: add password='mufg' to every document in the clients collection.

Usage:
    cd backend
    python scripts/set_client_passwords.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

import firebase_admin
from firebase_admin import credentials, firestore


def main() -> None:
    cred_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS", "secrets/firebase-credentials.json"
    )
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    docs = list(db.collection("clients").stream())
    if not docs:
        print("No clients found.")
        return

    for doc in docs:
        data = doc.to_dict()
        doc.reference.update({"password": "mufg"})
        print(f"  updated {doc.id} ({data.get('first_name')} {data.get('last_name')})")

    print(f"\nDone — set password='mufg' on {len(docs)} client(s).")


if __name__ == "__main__":
    main()
