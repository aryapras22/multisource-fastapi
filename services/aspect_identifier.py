# aspect_identifier.py
"""
Aspect identification for user story extraction using dependency parsing and WordNet.
Implements WHO, WHAT, and WHY aspect identification.
"""
from __future__ import annotations
from typing import List, Dict, Set, Optional
import re

import spacy
from spacy.tokens import Span, Token, Doc
from nltk.corpus import wordnet as wn

# ---------------- spaCy setup ----------------
nlp = spacy.load("en_core_web_lg")

# Constants
WN_ALLOWED_LEXNAMES_NOUNS = {"noun.person", "noun.group", "noun.artifact"}
WN_ALLOWED_LEXNAMES_VERBS = {
    "verb.cognition",
    "verb.communication",
    "verb.contact",
    "verb.creation",
    "verb.motion",
    "verb.perception",
    "verb.possession",
}


# ---------------- Utility Functions ----------------
def norm_space(s: str) -> str:
    """Normalize whitespace in string."""
    return re.sub(r"\s+", " ", (s or "").strip())


def clean_to_prefix(s: str) -> str:
    """Remove 'to' prefix and normalize spacing."""
    return norm_space(re.sub(r"^(to\s+)", "", s.strip(" .,:;!-"), flags=re.I))


# ---------------- WHO Aspect Identification ----------------
def identify_who_aspect(sent_span: Span) -> str:
    """
    Identify WHO aspect using dependency parsing and WordNet lexical categories.

    Args:
        sent_span: A spaCy Span representing a sentence

    Returns:
        The identified WHO aspect or 'user' as default
    """
    target_dependencies = {"nsubj", "nsubjpass", "dobj", "pobj"}
    target_lexnames = {"noun.person", "noun.group", "noun.artifact"}

    subject_object_tokens: List[Token] = []

    # Step 1: Collect tokens with target dependencies
    for token in sent_span:
        if token.dep_ in target_dependencies:
            subject_object_tokens.append(token)

    aspect_of_who: Set[str] = set()

    # Step 2: Check each token against criteria
    for token in subject_object_tokens:
        # Check if token is part of a person/org entity
        is_person_entity = False
        for ent in sent_span.doc.ents:
            if token.i >= ent.start and token.i < ent.end:
                if ent.label_ in {"PERSON", "ORG"}:
                    is_person_entity = True
                    break

        # Check if token is a pronoun
        is_a_pronoun = token.pos_ == "PRON"

        # Check if token belongs to WHO category via WordNet
        is_who_category = False
        token_synsets = wn.synsets(token.text.lower())
        for synset in token_synsets:
            lexname = synset.lexname()
            if lexname and lexname in target_lexnames:
                is_who_category = True
                break

        # If any condition is met, add to aspect_of_who
        if is_person_entity or is_a_pronoun or is_who_category:
            aspect_of_who.add(token.text)

    # Return first match or default to "user"
    if aspect_of_who:
        return list(aspect_of_who)[0]
    return "user"


# ---------------- WHAT Aspect Identification ----------------
def identify_what_aspect(sent_span: Span) -> List[Dict]:
    """
    Identify WHAT aspect using POS chunking patterns and WordNet verb lexnames.

    Args:
        sent_span: A spaCy Span representing a sentence

    Returns:
        List of candidates with text, strategy, and kind fields
    """
    all_candidates: List[Dict] = []
    toks = list(sent_span)
    i = 0

    # POS chunking: ADJ/VERB → PUNCT/PART/etc. → DET → NOUN/PROPN/ADV
    while i < len(toks):
        if toks[i].pos_ in {"ADJ", "VERB"}:
            phrase_start = i
            j = i

            # Collect ADJ/VERB tokens
            while j < len(toks) and toks[j].pos_ in {"ADJ", "VERB"}:
                j += 1

            # Skip connecting tokens
            while j < len(toks) and toks[j].pos_ in {
                "PUNCT",
                "PART",
                "ADP",
                "CCONJ",
                "SCONJ",
                "PRON",
            }:
                j += 1

            # Skip determiners
            while j < len(toks) and toks[j].pos_ == "DET":
                j += 1

            # Collect noun phrase
            noun_start = j
            while j < len(toks) and toks[j].pos_ in {"NOUN", "PROPN", "ADV"}:
                j += 1

            # If we found nouns after verbs/adjectives, create candidate
            if j > noun_start:
                span = clean_to_prefix(sent_span.doc[phrase_start:j].text)
                all_candidates.append(
                    {"text": span, "strategy": "pos_chunking", "kind": ""}
                )
                i = j
            else:
                i += 1
        else:
            i += 1

    # Filter candidates by WordNet verb lexnames
    final_list: List[Dict] = []
    for candidate in all_candidates:
        candidate_doc = nlp(candidate["text"])
        has_valid_verb = False

        for token in candidate_doc:
            if token.pos_ == "VERB":
                verb_synsets = wn.synsets(token.lemma_, pos=wn.VERB)

                for synset in verb_synsets:
                    if synset is None:
                        continue
                    lexname = synset.lexname()

                    if lexname in WN_ALLOWED_LEXNAMES_VERBS:
                        has_valid_verb = True
                        break

                if has_valid_verb:
                    break

        if has_valid_verb:
            final_list.append(candidate)

    # Sort by descending text length
    final_list.sort(key=lambda h: -len(h["text"]))

    # Remove duplicates while preserving order
    unique_results: Dict[str, Dict] = {}
    for hit in final_list:
        key = hit["text"].lower()
        if key not in unique_results:
            unique_results[key] = hit

    return list(unique_results.values())


# ---------------- WHY Aspect Identification ----------------
def identify_why_aspect(sent_span: Span, what_hits: List[Dict]) -> List[str]:
    """
    Identify WHY aspect based on causal relationships with WHAT aspects.

    Args:
        sent_span: A spaCy Span representing a sentence
        what_hits: List of WHAT aspect candidates

    Returns:
        List of unique purpose clauses
    """
    hits: List[str] = []
    what_texts = {hit["text"].lower() for hit in what_hits}

    for token in sent_span:
        # Check dependency
        if token.dep_ not in {"advcl", "xcomp", "ccomp"}:
            continue

        # Check POS
        if token.pos_ not in {"VERB", "ADJ", "NOUN"}:
            continue

        # Extract subtree text
        span = clean_to_prefix(" ".join(w.text for w in token.subtree))

        # Check minimum word count
        if len(span.split()) < 2:
            continue

        # Check if WHY clause includes WHAT text (causal relationship)
        span_lower = span.lower()
        includes_what = any(what_text in span_lower for what_text in what_texts)

        if includes_what:
            hits.append(span)
            break

    # Remove duplicates while preserving order (shortest first)
    uniq: Dict[str, str] = {}
    for h in sorted(hits, key=lambda h: len(h)):
        key = h.lower()
        if key not in uniq:
            uniq[key] = h

    return list(uniq.values())
