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

from dictionaries.default_dict import software_functionality_dict

# ---------------- spaCy setup ----------------
nlp = spacy.load("en_core_web_lg")


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
        # Check if token is a person/org entity
        is_person_entity = token.ent_type_ in {"PERSON", "ORG", "NORP"}

        # Check if token is a pronoun
        is_a_pronoun = token.pos_ == "PRON"

        # Check if token belongs to WHO category via WordNet
        is_who_category = False
        token_synsets = wn.synsets(token.text.lower())
        for synset in token_synsets:
            lexname = synset.lexname()  # type: ignore
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
def _check_if_phrase_is_software_related(
    phrase: str, min_similarity: float = 0.5
) -> bool:
    """
    Check if a phrase is related to software functionality using semantic similarity.

    Args:
        phrase: The text phrase to check
        min_similarity: Minimum similarity threshold

    Returns:
        True if phrase is software-related, False otherwise
    """
    phrase_doc = nlp(phrase)
    keyword_docs = [nlp(k) for k in software_functionality_dict]

    max_sim = 0.0
    for kd in keyword_docs:
        sim = phrase_doc.similarity(kd)
        if sim > max_sim:
            max_sim = sim

    return max_sim >= min_similarity


def _find_main_verb_phrase(doc: Doc) -> Optional[str]:
    """
    Find the main verb phrase in the document.

    Args:
        doc: A spaCy Doc

    Returns:
        The main verb phrase or None
    """
    for token in doc:
        if token.pos_ == "VERB" and token.dep_ in {"ROOT", "relcl", "ccomp"}:
            # Get the verb and its direct object/complement
            phrase_tokens = [token]
            for child in token.children:
                if child.dep_ in {"dobj", "attr", "acomp", "prt", "advmod"}:
                    phrase_tokens.append(child)

            if len(phrase_tokens) > 1:
                # Sort by token position
                phrase_tokens.sort(key=lambda t: t.i)
                return " ".join([t.text for t in phrase_tokens])
            else:
                return token.text
    return None


def _find_verb_noun_patterns(doc: Doc) -> List[str]:
    """
    Find simple Verb-Noun patterns in the document.

    Args:
        doc: A spaCy Doc

    Returns:
        List of verb-noun pattern strings
    """
    patterns = []

    for token in doc:
        if token.pos_ == "VERB":
            for child in token.children:
                if child.pos_ == "NOUN" and child.dep_ in {"dobj", "pobj", "attr"}:
                    patterns.append(f"{token.text} {child.text}")

    return patterns


def identify_what_aspect(text: str, min_similarity: float = 0.5) -> List[Dict]:
    """
    Identify WHAT aspect using verb phrases and patterns.

    Args:
        text: The text to analyze
        min_similarity: Minimum similarity threshold for software relevance

    Returns:
        List of candidates sorted by priority and length
    """
    doc = nlp(text)
    all_candidates: List[Dict] = []

    # Find main verb phrase
    action = _find_main_verb_phrase(doc)
    if action:
        all_candidates.append({"text": action, "priority": "general"})

    # Find Verb-Noun patterns
    patterns = _find_verb_noun_patterns(doc)
    for pattern in patterns:
        all_candidates.append({"text": pattern, "priority": "pattern"})

    # Check software relevance and build final list
    final_list: List[Dict] = []
    for candidate in all_candidates:
        is_relevant = _check_if_phrase_is_software_related(
            candidate["text"], min_similarity
        )
        kind = "software-related" if is_relevant else "general"

        final_list.append(
            {"text": candidate["text"], "priority": candidate["priority"], "kind": kind}
        )

    # Sort by priority (pattern > general) and then by descending text length
    priority_order = {"pattern": 0, "general": 1}
    final_list.sort(
        key=lambda x: (priority_order.get(x["priority"], 2), -len(x["text"]))
    )

    # Remove duplicates while preserving order
    seen = set()
    unique_results = []
    for item in final_list:
        text_lower = item["text"].lower()
        if text_lower not in seen:
            seen.add(text_lower)
            unique_results.append(item)

    return unique_results


# ---------------- WHY Aspect Identification ----------------
def _clean_up_text(text: str) -> str:
    """
    Clean up text by removing extra whitespace and punctuation.

    Args:
        text: The text to clean

    Returns:
        Cleaned text
    """
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove leading/trailing punctuation
    text = text.strip(".,;:!?")
    return text


def identify_why_aspect(text: str) -> List[str]:
    """
    Identify WHY aspect using dependency parsing for purpose clauses.

    Args:
        text: The text to analyze

    Returns:
        List of unique purpose clauses sorted by length (shorter first)
    """
    doc = nlp(text)
    candidates: List[str] = []

    target_dependencies = {"advcl", "xcomp", "ccomp"}

    for token in doc:
        if token.dep_ in target_dependencies:
            # Get the full text of the token's subtree
            purpose_clause = " ".join([t.text for t in token.subtree])

            # Clean up the clause
            cleaned_clause = _clean_up_text(purpose_clause)

            # Check if cleaned clause has 2 or more words
            if len(cleaned_clause.split()) >= 2:
                candidates.append(cleaned_clause)
                # Stop searching after first match (as per pseudocode)
                break

    # Sort by text length (shorter is better)
    candidates.sort(key=len)

    # Remove duplicates while preserving order
    seen = set()
    unique_results = []
    for clause in candidates:
        clause_lower = clause.lower()
        if clause_lower not in seen:
            seen.add(clause_lower)
            unique_results.append(clause)

    return unique_results
