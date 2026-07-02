import sys, os
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from app.services.qdrant_service import search_faq, get_collection_count

count = get_collection_count()
print("Vectors in Qdrant:", count)
print()

tests = [
    "What is NIPM?",
    "How do I register on NIPM portal?",
    "What documents are required for registration?",
    "Tell me about NIPM",
]

for q in tests:
    print("Query:", q)
    result = search_faq(q)
    if result["matched"]:
        score = result["score"]
        ans = result["answer"][:120]
        print("  MATCH (" + str(score) + "%): " + ans)
    else:
        print("  NO MATCH")
    print()
