# user_story_extractor.py
from __future__ import annotations
from typing import List, Dict, Optional, Literal, Iterable
import re
import uuid

import spacy
from spacy.tokens import Doc, Span

from dictionaries.default_dict import software_functionality_dict
from models import UserStoryModel
from db import user_stories_collection

# Import aspect identification functions
from services.aspect_identifier import (
    identify_who_aspect,
    identify_what_aspect,
    identify_why_aspect,
    nlp,  # Reuse the same spaCy model
)

import nltk

nltk.download("wordnet", quiet=True)
nltk.download("omw-1.4", quiet=True)
nltk.download("stopwords", quiet=True)


# ---------------- Utility functions ----------------
def norm_space(s: str) -> str:
    """Normalize whitespace in a string."""
    return re.sub(r"\s+", " ", (s or "").strip())


# ---------------- Per-source extractors ----------------
def _extract_from_sentence(
    sent_text: str, raw_text: str = "", source: str = "review"
) -> Optional[Dict]:
    """Extract user story from a single sentence."""
    doc = nlp(sent_text)
    sent_span = doc[:]

    # Extract WHAT (required) - use aspect_identifier
    what_candidates = identify_what_aspect(sent_span)
    if not what_candidates:
        return None

    # Pick the first candidate
    what = what_candidates[0]["text"] if what_candidates else None
    if not what:
        return None

    # Extract WHO - use aspect_identifier
    who = identify_who_aspect(sent_span)

    # For tweets, check for @mentions
    if source == "tweet" and raw_text:
        m = re.search(r"(?<!\w)@(\w+)", raw_text)
        if m:
            who = f"@{m.group(1)}"

    # Extract WHY - use aspect_identifier (requires what_candidates)
    why_candidates = identify_why_aspect(sent_span, what_candidates)
    why = why_candidates[0] if why_candidates else None

    return {
        "who": who,
        "what": what,
        "why": why,
        "full_sentence": sent_text.strip(),
    }


def _extract_from_review(content: str, min_similarity: float = 0.5) -> List[Dict]:
    """Extract user stories from review content."""
    doc = nlp(content)
    cands: List[Dict] = []

    for sent in doc.sents:
        result = _extract_from_sentence(sent.text, source="review")
        if result:
            cands.append(result)

    return cands


def _extract_from_news(content: str, min_similarity: float = 0.5) -> List[Dict]:
    """Extract user stories from news content."""
    doc = nlp(content)
    cands: List[Dict] = []

    for sent in doc.sents:
        result = _extract_from_sentence(sent.text, source="news")
        if result:
            cands.append(result)

    return cands


def _extract_from_tweet(content: str, min_similarity: float = 0.5) -> List[Dict]:
    """Extract user stories from tweet content."""
    raw = content
    doc = nlp(content)
    cands: List[Dict] = []

    for sent in doc.sents:
        result = _extract_from_sentence(sent.text, raw_text=raw, source="tweet")
        if result:
            cands.append(result)

    return cands


# ---------------- Public API ----------------
def extract_user_stories(
    *,
    source: Literal["review", "news", "tweet"],
    source_id: str,
    content: str,
    project_id: str,
    min_similarity: float = 0.70,
    dedupe: bool = True,
) -> List[UserStoryModel]:
    """
    Extract user stories from content using rule-based approach.

    Args:
        source: Type of source ('review', 'news', or 'tweet')
        source_id: ID of the source document
        content: Text content to extract from
        project_id: Project ID for organizing user stories
        min_similarity: Minimum similarity threshold for software context filtering
        dedupe: Whether to remove duplicate user stories

    Returns:
        List of UserStoryModel objects
    """
    if not content or not isinstance(content, str):
        return []

    # 1) Extract candidates
    if source == "review":
        candidates = _extract_from_review(content, min_similarity)
    elif source == "news":
        candidates = _extract_from_news(content, min_similarity)
    elif source == "tweet":
        candidates = _extract_from_tweet(content, min_similarity)
    else:
        raise ValueError("source must be one of: 'review' | 'news' | 'tweet'")

    # 2) Filter by domain context
    # filtered = _filter_by_software_context(
    #     candidates, software_functionality_dict, min_similarity
    # )

    # 3) De-duplicate (stable order)
    if dedupe:
        seen = set()
        uniq = []
        for c in candidates:
            key = (
                c["who"].lower(),
                c["what"].lower(),
                (c.get("why") or "").lower(),
                c["full_sentence"].lower(),
            )
            if key not in seen:
                seen.add(key)
                uniq.append(c)
        filtered = uniq

    if not filtered:
        return []

    # 4) Create UserStoryModel objects and insert into database
    docs = []
    models: List[UserStoryModel] = []
    for c in filtered:
        user_story_id = str(uuid.uuid4())
        m = UserStoryModel(
            _id=user_story_id,
            who=c["who"],
            what=c["what"],
            why=c.get("why"),
            full_sentence=c["full_sentence"],
            similarity_score=c.get("similarity", 0.0),
            source=source,
            source_id=source_id,
            project_id=project_id,
        )
        models.append(m)
        docs.append(
            {
                "_id": user_story_id,
                "who": m.who,
                "what": m.what,
                "why": m.why,
                "full_sentence": m.full_sentence,
                "similarity_score": m.similarity_score,
                "source": m.source,
                "source_id": m.source_id,
                "project_id": m.project_id,
            }
        )

    if docs:
        user_stories_collection.insert_many(docs)

    return models
