import uuid
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.db.base import SessionLocal
from app.models.faq import Faq
from app.services.qdrant_service import create_collection, add_faq_to_qdrant


# ─────────────────────────────────────────────────────────────
# STEP 1 — Parse the NIPM FAQ Markdown Document
# ─────────────────────────────────────────────────────────────

def parse_nipm_faq(filepath: str):
    """
    Parses the NIPM_FAQ_Document.md file.
    Detects:
      - Category from ## headings  e.g. ## 1. General / About NIPM
      - Question from ### Q1. ...
      - Answer from **A:** ... (multi-line until next Q or ##)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    faqs = []
    current_category = "General"

    # Split by lines for processing
    lines = content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detect category heading  ## 1. General / About NIPM
        if line.startswith("## ") and not line.startswith("## Table"):
            # Remove the ## and number prefix  e.g. "## 1. General / About NIPM"
            category_raw = re.sub(r"^##\s+\d+\.\s*", "", line).strip()
            current_category = category_raw
            i += 1
            continue

        # Detect question line  ### Q1. What is NIPM?
        if re.match(r"^###\s+Q\d+\.", line):
            question = re.sub(r"^###\s+Q\d+\.\s*", "", line).strip()

            # Collect answer lines starting from **A:**
            answer_lines = []
            i += 1
            answer_started = False

            while i < len(lines):
                current = lines[i].strip()

                # Stop at next question or next category
                if re.match(r"^###\s+Q\d+\.", current) or current.startswith("## "):
                    break

                # Detect start of answer
                if current.startswith("**A:**"):
                    answer_started = True
                    # Get text on the same line after **A:**
                    inline = current.replace("**A:**", "").strip()
                    if inline:
                        answer_lines.append(inline)
                    i += 1
                    continue

                if answer_started:
                    # Skip dividers and empty lines at start
                    if current == "---":
                        break
                    # Skip emoji-only lines and learn more lines
                    if current.startswith("🔗") or current.startswith("> ⚠️"):
                        i += 1
                        continue
                    # Add content lines
                    if current:
                        # Clean markdown bold/italic formatting
                        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", current)
                        cleaned = re.sub(r"\*(.*?)\*", r"\1", cleaned)
                        # Clean markdown table separators
                        if re.match(r"^\|[-| ]+\|$", cleaned):
                            i += 1
                            continue
                        # Clean markdown links [text](url) → text
                        cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
                        # Clean blockquotes
                        cleaned = re.sub(r"^>\s*", "", cleaned)
                        answer_lines.append(cleaned)

                i += 1

            # Build clean answer text
            answer = " ".join(answer_lines).strip()

            # Remove extra spaces
            answer = re.sub(r"\s+", " ", answer)

            if question and answer and len(answer) > 10:
                faqs.append({
                    "question": question,
                    "answer": answer,
                    "category": current_category
                })

            continue  # Don't increment i — already moved inside while loop

        i += 1

    return faqs


# ─────────────────────────────────────────────────────────────
# STEP 2 — Seed FAQs into PostgreSQL + Qdrant
# ─────────────────────────────────────────────────────────────

def seed_faqs(faqs: list):
    db = SessionLocal()

    # Create Qdrant collection if not exists
    create_collection()

    added = 0
    skipped = 0

    print(f"\nStarting seeder — {len(faqs)} FAQs to process...\n")

    for item in faqs:
        question = item.get("question", "").strip()
        answer = item.get("answer", "").strip()
        category = item.get("category", "General")

        if not question or not answer:
            skipped += 1
            continue

        # Check if FAQ already exists in PostgreSQL (avoid duplicates)
        existing = db.query(Faq).filter(Faq.question == question).first()
        if existing:
            print(f"  [SKIP] Already exists: {question[:70]}")
            skipped += 1
            continue

        # Save to PostgreSQL
        faq = Faq(
            id=str(uuid.uuid4()),
            question=question,
            answer=answer,
            category=category,
            is_active=True
        )
        db.add(faq)
        db.commit()
        db.refresh(faq)

        # Save embedding to Qdrant using Sentence Transformers
        add_faq_to_qdrant(
            faq_id=faq.id,
            question=faq.question,
            answer=faq.answer,
            category=faq.category
        )

        print(f"  [ADDED] [{category[:25]}] {question[:70]}")
        added += 1

    db.close()

    print(f"\n{'='*60}")
    print(f"  Seeding complete!")
    print(f"  Total processed : {len(faqs)}")
    print(f"  Added           : {added}")
    print(f"  Skipped         : {skipped}")
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────
# STEP 3 — Run
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # Path to the FAQ markdown file
    # Place NIPM_FAQ_Document.md in the same folder as this script
    faq_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "NIPM_FAQ_Document.md")

    if not os.path.exists(faq_file):
        print(f"ERROR: FAQ file not found at {faq_file}")
        print("Please place NIPM_FAQ_Document.md in the server folder and run again.")
        sys.exit(1)

    print(f"Reading FAQs from: {faq_file}")
    faqs = parse_nipm_faq(faq_file)
    print(f"Parsed {len(faqs)} FAQs from document\n")

    # Preview first 3 parsed FAQs before seeding
    print("Preview of first 3 parsed FAQs:")
    print("-" * 60)
    for faq in faqs[:3]:
        print(f"  Category : {faq['category']}")
        print(f"  Question : {faq['question']}")
        print(f"  Answer   : {faq['answer'][:120]}...")
        print()

    # Confirm before seeding
    confirm = input("Proceed with seeding all FAQs into PostgreSQL and Qdrant? (yes/no): ")
    if confirm.lower() != "yes":
        print("Seeding cancelled.")
        sys.exit(0)

    seed_faqs(faqs)