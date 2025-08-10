# user_story_extractor.py
from __future__ import annotations
from typing import List, Dict, Optional, Literal, Iterable, Tuple
import re
import uuid
from bson import ObjectId

import spacy
from spacy.matcher import Matcher
from spacy.tokens import Doc, Span

from dictionaries.default_dict import software_functionality_dict
from models import UserStoryModel, PyObjectId
from db import user_stories_collection

# ---------------- spaCy setup ----------------
nlp = spacy.load("en_core_web_lg")
nlp.add_pipe("merge_noun_chunks", before="ner")

# POS-patterns (same spirit as your original)
matcher = Matcher(nlp.vocab)
_patterns = [
    [{"POS": "VERB"}, {"POS": "ADJ"}, {"POS": "NOUN"}],  # VERB ADJ NOUN
    [{"POS": "VERB"}, {"POS": "NOUN"}],  # VERB NOUN
    [{"POS": "VERB"}, {"POS": "ADV", "OP": "?"}, {"POS": "ADJ"}, {"POS": "NOUN"}],
    [{"POS": "NOUN"}, {"POS": "VERB"}],  # NOUN VERB
]
for i, p in enumerate(_patterns):
    matcher.add(f"GOAL_PATTERN_{i+1}", [p])

# ---------------- WHY extraction (no cleaning) ----------------
_SO_THAT_RE = re.compile(r"\bso that\b\s+(?P<why>.+)", flags=re.I)
_BECAUSE_RE = re.compile(r"\bbecause\b\s+(?P<why>.+)", flags=re.I)
_SO_I_CAN_RE = re.compile(r"\bso (?:I|we) can\b\s+(?P<why>.+)", flags=re.I)
_TO_VERB_RE = re.compile(
    r"\bto\s+(?P<why>(?:\w+\s*){1,8})", flags=re.I
)  # short verb phrase


def _extract_why(sentence_text: str) -> Optional[str]:
    s = sentence_text.strip()
    for rx in (_SO_THAT_RE, _SO_I_CAN_RE, _BECAUSE_RE, _TO_VERB_RE):
        m = rx.search(s)
        if m:
            why = m.group("why").strip().rstrip(".!?;,:")
            return why[:200]
    return None


# ---------------- WHO extraction (source-specific) ----------------
def _who_from_news_sentence(sent_span: Span) -> str:
    # Prefer PERSON/ORG/NORP entities in the sentence span
    for ent in sent_span.ents:
        if ent.label_ in {"PERSON", "ORG", "NORP"}:
            return ent.text
    return "user"


def _who_from_review_sentence(_: Span) -> str:
    # Reviews typically represent end users
    return "user"


def _who_from_tweet_sentence(sent_span: Span, raw_text: str) -> str:
    # If tweet mentions someone, use the first @mention as who; else default
    m = re.search(r"(?<!\w)@(\w+)", raw_text)
    if m:
        return f"@{m.group(1)}"
    if any(t.lower_ in {"i", "we"} for t in sent_span):
        return "user"
    return "user"


# ---------------- WHAT extraction ----------------
def _spacy_match_what(doc: Doc) -> List[Tuple[Span, Span]]:
    """Return list of (what_span, sentence_span) by POS patterns."""
    matched: List[Tuple[Span, Span]] = []
    for _, start, end in matcher(doc):
        span = doc[start:end]
        sent = span.sent if span.sent is not None else span
        matched.append((span, sent))
    return matched


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


# ---------------- per-source extractors (NO cleaning) ----------------
def _extract_from_review(content: str) -> List[Dict]:
    doc = nlp(content)  # content already cleaned upstream
    cands: List[Dict] = []
    for what_span, sent in _spacy_match_what(doc):
        cands.append(
            {
                "who": _who_from_review_sentence(sent),
                "what": what_span.text.strip(),
                "why": _extract_why(sent.text),
                "full_sentence": sent.text.strip(),
            }
        )
    return cands


def _extract_from_news(content: str) -> List[Dict]:
    doc = nlp(content)  # content already cleaned upstream
    cands: List[Dict] = []
    for what_span, sent in _spacy_match_what(doc):
        cands.append(
            {
                "who": _who_from_news_sentence(sent),
                "what": what_span.text.strip(),
                "why": _extract_why(sent.text),
                "full_sentence": sent.text.strip(),
            }
        )
    return cands


def _extract_from_tweet(content: str) -> List[Dict]:
    raw = content  # keep raw to find @mentions; no cleaning here
    doc = nlp(content)
    cands: List[Dict] = []
    for what_span, sent in _spacy_match_what(doc):
        cands.append(
            {
                "who": _who_from_tweet_sentence(sent, raw),
                "what": what_span.text.strip(),
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
        candidates = _extract_from_review(content)
    elif source == "news":
        candidates = _extract_from_news(content)
    elif source == "tweet":
        candidates = _extract_from_tweet(content)
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
