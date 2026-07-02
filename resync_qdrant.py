"""
resync_qdrant.py
────────────────
Run this ONCE to fix the Qdrant vector store.

Problem: previous code used random UUIDs for Qdrant point IDs, meaning
every seed run created DUPLICATE vectors and there was no way to
guarantee the right FAQ vectors were stored.

This script:
  1. Drops the existing Qdrant collection (removes all bad/duplicate vectors)
  2. Re-creates the collection
  3. Re-embeds and re-inserts every active FAQ from PostgreSQL using
     the correct faq_id as the Qdrant point ID

Usage:
    cd d:\\nipm\\server
    .\\venv\\Scripts\\python resync_qdrant.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.db.base import SessionLocal
from app.models.faq import Faq
from app.services.qdrant_service import (
    client,
    COLLECTION_NAME,
    create_collection,
    add_faq_to_qdrant,
    get_collection_count,
)


def resync():
    db = SessionLocal()
    try:
        # ── Step 1: Count FAQs in PostgreSQL ──────────────────────────────
        faqs = db.query(Faq).filter(Faq.is_active == True).all()
        print(f"\n[PostgreSQL] Found {len(faqs)} active FAQs\n")

        if not faqs:
            print("No active FAQs found in PostgreSQL. Nothing to sync.")
            return

        # ── Step 2: Drop + recreate Qdrant collection ─────────────────────
        existing = [c.name for c in client.get_collections().collections]
        if COLLECTION_NAME in existing:
            print(f"[Qdrant] Dropping collection '{COLLECTION_NAME}'...")
            client.delete_collection(COLLECTION_NAME)
            print(f"[Qdrant] Collection dropped.\n")

        create_collection()
        print()

        # ── Step 3: Re-insert every FAQ ───────────────────────────────────
        print(f"[Qdrant] Re-embedding and inserting {len(faqs)} FAQs...\n")
        for i, faq in enumerate(faqs, 1):
            add_faq_to_qdrant(
                faq_id=faq.id,
                question=faq.question,
                answer=faq.answer,
                category=faq.category or "General"
            )
            if i % 10 == 0 or i == len(faqs):
                print(f"  Progress: {i}/{len(faqs)}")

        # ── Step 4: Verify ────────────────────────────────────────────────
        count = get_collection_count()
        print(f"\n{'='*60}")
        print(f"  Resync complete!")
        print(f"  FAQs in PostgreSQL : {len(faqs)}")
        print(f"  Vectors in Qdrant  : {count}")
        print(f"{'='*60}\n")

        if count != len(faqs):
            print("WARNING: Vector count doesn't match FAQ count!")
            print("   Some FAQs may not have been embedded properly.")
        else:
            print("SUCCESS: All FAQs successfully synced to Qdrant!\n")

    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("  NIPM FAQ — Qdrant Resync Tool")
    print("=" * 60)
    resync()
