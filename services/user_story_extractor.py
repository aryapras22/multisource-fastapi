# user_story_extractor.py
from __future__ import annotations
from typing import List, Dict, Optional, Literal, Iterable, Tuple
import re
import uuid
from bson import ObjectId

import spacy
from spacy.tokens import Doc, Span

from dictionaries.default_dict import software_functionality_dict
from models import UserStoryModel, PyObjectId
from db import user_stories_collection
from services.aspect_identifier import (
    identify_who_aspect,
    identify_what_aspect,
    identify_why_aspect,
)

import nltk

nltk.download("wordnet")
nltk.download("omw-1.4")

# ---------------- spaCy setup ----------------
nlp = spacy.load("en_core_web_lg")

# Note: Matcher no longer used as WHAT extraction is handled by aspect_identifier


# ---------------- WHY extraction ----------------
def _extract_why(sentence_text: str) -> Optional[str]:
    """
    Extract WHY aspect using the new aspect_identifier.
    Returns the first (shortest) why clause or None.
    """
    why_candidates = identify_why_aspect(sentence_text)
    if why_candidates:
        return why_candidates[0]  # Return the shortest/first candidate
    return None


# ---------------- WHO extraction (source-specific) ----------------
def _who_from_news_sentence(sent_span: Span) -> str:
    return identify_who_aspect(sent_span)


def _who_from_review_sentence(sent_span: Span) -> str:
    return identify_who_aspect(sent_span)


def _who_from_tweet_sentence(sent_span: Span, raw_text: str) -> str:
    # If tweet mentions someone, use the first @mention as who; else default
    m = re.search(r"(?<!\w)@(\w+)", raw_text)
    if m:
        return f"@{m.group(1)}"
    # Otherwise use WordNet-based identification
    return identify_who_aspect(sent_span)


# ---------------- WHAT extraction ----------------
def _extract_what_from_sentence(
    sent_text: str, min_similarity: float = 0.5
) -> Optional[str]:
    """
    Extract WHAT aspect using the new aspect_identifier.
    Returns the best matching what clause or None.
    """
    what_candidates = identify_what_aspect(sent_text, min_similarity)
    if what_candidates:
        # Return the first (highest priority) candidate
        return what_candidates[0]["text"]
    return None


# ---------------- software context filter ----------------
def _filter_by_software_context(
    cands: List[Dict], keywords: Iterable[str], threshold: float
) -> List[Dict]:
    keyword_docs = [nlp(k) for k in keywords]
    kept = []
    for c in cands:
        what_doc = nlp(c["what"])
        max_sim = 0.0
        for kd in keyword_docs:
            sim = what_doc.similarity(kd)
            if sim > max_sim:
                max_sim = sim
        if max_sim >= threshold:
            kept.append({**c, "similarity": float(max_sim)})
    return kept


# ---------------- per-source extractors ----------------
def _extract_from_review(content: str, min_similarity: float = 0.5) -> List[Dict]:
    doc = nlp(content)  # content already cleaned upstream
    cands: List[Dict] = []
    for sent in doc.sents:
        what = _extract_what_from_sentence(sent.text, min_similarity)
        if what:  # Only create candidate if we found a WHAT
            cands.append(
                {
                    "who": _who_from_review_sentence(sent),
                    "what": what,
                    "why": _extract_why(sent.text),
                    "full_sentence": sent.text.strip(),
                }
            )
    return cands


def _extract_from_news(content: str, min_similarity: float = 0.5) -> List[Dict]:
    doc = nlp(content)  # content already cleaned upstream
    cands: List[Dict] = []
    for sent in doc.sents:
        what = _extract_what_from_sentence(sent.text, min_similarity)
        if what:  # Only create candidate if we found a WHAT
            cands.append(
                {
                    "who": _who_from_news_sentence(sent),
                    "what": what,
                    "why": _extract_why(sent.text),
                    "full_sentence": sent.text.strip(),
                }
            )
    return cands


def _extract_from_tweet(content: str, min_similarity: float = 0.5) -> List[Dict]:
    raw = content  # keep raw to find @mentions
    doc = nlp(content)
    cands: List[Dict] = []
    for sent in doc.sents:
        what = _extract_what_from_sentence(sent.text, min_similarity)
        if what:  # Only create candidate if we found a WHAT
            cands.append(
                {
                    "who": _who_from_tweet_sentence(sent, raw),
                    "what": what,
                    "why": _extract_why(sent.text),
                    "full_sentence": sent.text.strip(),
                }
            )
    return cands


# ---------------- public API ----------------
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
    Input: ONE source content string (already cleaned upstream).
    Output: list of UserStoryModel, also inserted into user_stories_collection.

    - Different extractor per source.
    - Optional filtering by software functionality context (similarity).
    - Optional de-duplication by (who, what, why, full_sentence).
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
    filtered = _filter_by_software_context(
        candidates, software_functionality_dict, min_similarity
    )

    # 3) De-duplicate (stable order)
    if dedupe:
        seen = set()
        uniq = []
        for c in filtered:
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
            similarity_score=c["similarity"],
            source=source,
            source_id=source_id,
            project_id=project_id,  # added
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
                "project_id": m.project_id,  # added
            }
        )
    if docs:
        user_stories_collection.insert_many(docs)
    return models
