import json
import os
import requests 
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ["QWEN_BASE_URL"].rstrip("/")
MODEL = os.environ["QWEN_MODEL"]

DOCUMENTS = {
    "doc_1": {
        "title": "PaperParse: input support",
        "text": (
            "PaperParse is a fictional library. It extracts embedded text "
            "from digital PDFs. Scanned PDFs require the optional ScanBridge "
            "OCR integration."
        ),
    },
    "doc_2": {
        "title": "PaperParse: tables and OCR limitations",
        "text": (
            "PaperParse extracts tables from digital PDFs. With ScanBridge, "
            "it can process scanned tables, but merged cells and low-quality "
            "scans may require manual correction."
        ),
    },
    "doc_3": {
        "title": "VisionPages: capabilities and limitations",
        "text": (
            "VisionPages is a fictional library with built-in OCR for "
            "scanned PDFs and table extraction. Its documentation reports "
            "difficulty with handwritten text and tables spanning pages."
        ),
    },
}

def search_sources(query: str) -> dict:
    """ Search the local fictional doc"""
    terms = set(query.lower().split())
    matches = []
    for source_id, document in DOCUMENTS.items():
        searchable = f"{document['title']} {document['text']}".lower()
        score = sum(term in searchable for term in terms)
        if score > 0:
            matches.append({
                "source_id": source_id,
                "title": document["title"],
                "snippet": document["text"],
                "score": score
            })

    matches.sort(key=lambda item: item["score"], reverse=True)
    return {"results": matches[:3]}

def read_source(source_id: str) -> dict:
    """Read a document using its stabloe source identifier"""
    document = DOCUMENTS.get(source_id)
    if document is None:
        return {
            "error": "source not found",
            "source_id": source_id
        }
    return {
        "source_id": source_id,
        "title": document["title"],
        "text": document["text"]
    }