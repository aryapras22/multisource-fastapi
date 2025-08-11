# usecase_diagram_service.py
from __future__ import annotations

from typing import Dict, List, Tuple, Set
import re
from datetime import datetime
from bson import ObjectId
from plantuml import PlantUML

from db import (
    user_stories_collection,
    use_cases_collection,
    ai_stories_collection,
    ai_use_cases_collection,
)

# ---- Configs ----
PLANTUML_SERVER = "http://www.plantuml.com/plantuml/img/"
MAX_USECASES_PER_DIAGRAM = 6  # chunking size for readability

# ---- Helpers ----

_ws_re = re.compile(r"\s+")


def _normalize_key(s: str) -> str:
    """Light normalize for dedup keys: lowercase + collapse spaces + strip quotes/punct at ends."""
    if not s:
        return ""
    s2 = s.strip().strip("\"'" "“”‘’()[]{}")
    s2 = _ws_re.sub(" ", s2)
    return s2.lower()


def _alias(prefix: str, idx: int) -> str:
    """Generate short PlantUML-safe aliases."""
    return f"{prefix}{idx}"


def _chunk(seq: List[str], size: int) -> List[List[str]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


# ---- Core build ----


def _collect_from_stories(project_id: str):
    """
    Pull all stories for a project_id and produce:
      - usecase_map: key -> {label, sentences, whys}
      - actor_set: set of actor labels
      - edges: set of (actor_label, usecase_key)
    """
    cursor = user_stories_collection.find({"project_id": project_id})
    usecase_map: Dict[str, Dict] = {}
    actor_set: Set[str] = set()
    edges: Set[Tuple[str, str]] = set()

    for s in cursor:
        who = (s.get("who") or "user").strip()
        what = (s.get("what") or "").strip()
        # full_sentence = (s.get("full_sentence") or "").strip()
        why = s.get("why") or None

        if not what:
            continue

        actor_label = _ws_re.sub(" ", who).strip() or "user"
        actor_set.add(actor_label)

        key = _normalize_key(what)
        if key not in usecase_map:
            # Keep the first-seen phrasing as the label
            usecase_map[key] = {
                "label": what,
                "sentences": [],
                "whys": [],
            }
        # if full_sentence:
        #     if full_sentence not in usecase_map[key]["sentences"]:
        #         usecase_map[key]["sentences"].append(full_sentence)
        if why:
            if why not in usecase_map[key]["whys"]:
                usecase_map[key]["whys"].append(why)

        edges.add((actor_label, key))

    return usecase_map, actor_set, edges


def _render_puml_chunks(
    project_id: str,
    usecase_map: Dict[str, Dict],
    actor_set: Set[str],
    edges: Set[Tuple[str, str]],
) -> List[str]:
    """
    Split by use cases into chunks. Each chunk includes:
      - Only use cases in that chunk
      - Only edges for those use cases
      - Only actors that connect in this chunk
    """
    usecase_keys = list(usecase_map.keys())
    chunks = _chunk(usecase_keys, MAX_USECASES_PER_DIAGRAM)
    diagrams: List[str] = []

    for ci, ckeys in enumerate(chunks, start=1):
        # Assign stable aliases for actors & use cases (per-chunk)
        actor_alias: Dict[str, str] = {}
        uc_alias: Dict[str, str] = {}
        actor_idx = 1
        uc_idx = 1

        # Collect chunk edges and the actors needed
        chunk_edges: List[Tuple[str, str]] = []
        for actor_label, uc_key in edges:
            if uc_key in ckeys:
                chunk_edges.append((actor_label, uc_key))

        # Assign aliases for use cases first (we know the set)
        for uc_key in ckeys:
            uc_alias[uc_key] = _alias("U", uc_idx)
            uc_idx += 1

        # Assign aliases for the actors actually used in this chunk
        actors_in_chunk: List[str] = []
        for actor_label, uc_key in chunk_edges:
            if actor_label not in actor_alias:
                actor_alias[actor_label] = _alias("A", actor_idx)
                actors_in_chunk.append(actor_label)
                actor_idx += 1

        # Build PlantUML
        lines = []
        lines.append("@startuml")
        lines.append("left to right direction")
        lines.append(f"title Project: {project_id} (part {ci}/{len(chunks)})")

        # Declare actors
        for a in actors_in_chunk:
            alias = actor_alias[a]
            # Quote the label to keep spaces/case
            lines.append(f'actor "{a}" as {alias}')

        # Declare use cases + optional notes (merge of whys/sentences)
        for uc_key in ckeys:
            alias = uc_alias[uc_key]
            label = usecase_map[uc_key]["label"]
            lines.append(f"({label}) as {alias}")

        # Edges
        for actor_label, uc_key in chunk_edges:
            a = actor_alias[actor_label]
            u = uc_alias[uc_key]
            lines.append(f"{a} --> {u}")

        lines.append("@enduml")
        diagrams.append("\n".join(lines))

    return diagrams


def create_use_case_diagrams_by_project(project_id: str) -> dict:
    """
    Single-parameter API: project_id.
    - Reads user_stories_collection
    - Merges duplicate use cases by normalized 'what'
    - Builds PlantUML diagrams (chunked)
    - Returns PUML text + image URLs
    - Upserts into use_cases_collection (one doc per project_id)
    """
    usecase_map, actor_set, edges = _collect_from_stories(project_id)

    if not usecase_map:
        return {
            "project_id": project_id,
            "diagrams_puml": [],
            "diagrams_url": [],
            "stats": {"actors": 0, "usecases": 0, "edges": 0},
        }

    puml_list = _render_puml_chunks(project_id, usecase_map, actor_set, edges)

    # Resolve URLs via PlantUML server
    client = PlantUML(url=PLANTUML_SERVER)
    urls = [client.get_url(puml) for puml in puml_list]

    # (Optional) persist summary in use_cases_collection
    doc = {
        "_id": ObjectId(),  # new snapshot each time; change to upsert if you want a single doc
        "project_id": project_id,
        "generated_at": datetime.utcnow(),
        "diagrams_puml": puml_list,
        "diagrams_url": urls,
        "stats": {
            "actors": len(actor_set),
            "usecases": len(usecase_map),
            "edges": len(edges),
        },
    }
    use_cases_collection.insert_one(doc)

    return {
        "project_id": project_id,
        "diagrams_puml": puml_list,
        "diagrams_url": urls,
        "stats": {
            "actors": len(actor_set),
            "usecases": len(usecase_map),
            "edges": len(edges),
        },
    }


def _collect_from_ai_stories(project_id: str):
    """
    Pull all AI-generated stories for a project_id and produce:
      - usecase_map: key -> {label, sentences, whys}
      - actor_set: set of actor labels
      - edges: set of (actor_label, usecase_key)
    """
    cursor = ai_stories_collection.find({"project_id": project_id})
    usecase_map: Dict[str, Dict] = {}
    actor_set: Set[str] = set()
    edges: Set[Tuple[str, str]] = set()

    for s in cursor:
        who = (s.get("who") or "user").strip()
        what = (s.get("what") or "").strip()
        why = s.get("why") or None

        if not what:
            continue

        actor_label = _ws_re.sub(" ", who).strip() or "user"
        actor_set.add(actor_label)

        key = _normalize_key(what)
        if key not in usecase_map:
            usecase_map[key] = {
                "label": what,
                "sentences": [],
                "whys": [],
            }
        if why:
            if why not in usecase_map[key]["whys"]:
                usecase_map[key]["whys"].append(why)

        edges.add((actor_label, key))

    return usecase_map, actor_set, edges


def create_use_case_diagrams_from_ai_stories(project_id: str) -> dict:
    """
    Creates use case diagrams from AI-generated user stories:
    - Reads ai_user_stories_collection
    - Merges duplicate use cases by normalized 'what'
    - Builds PlantUML diagrams (chunked)
    - Returns PUML text + image URLs
    - Upserts into use_cases_collection (one doc per project_id)
    """
    usecase_map, actor_set, edges = _collect_from_ai_stories(project_id)

    if not usecase_map:
        return {
            "project_id": project_id,
            "diagrams_puml": [],
            "diagrams_url": [],
            "stats": {"actors": 0, "usecases": 0, "edges": 0},
        }

    puml_list = _render_puml_chunks(project_id, usecase_map, actor_set, edges)

    # Resolve URLs via PlantUML server
    client = PlantUML(url=PLANTUML_SERVER)
    urls = [client.get_url(puml) for puml in puml_list]

    # Store in use_cases_collection with source indicator
    doc = {
        "_id": ObjectId(),
        "project_id": project_id,
        "generated_at": datetime.utcnow(),
        "source": "ai_generated",  # Indicate this is from AI stories
        "diagrams_puml": puml_list,
        "diagrams_url": urls,
        "stats": {
            "actors": len(actor_set),
            "usecases": len(usecase_map),
            "edges": len(edges),
        },
    }
    ai_use_cases_collection.insert_one(doc)

    return {
        "project_id": project_id,
        "diagrams_puml": puml_list,
        "diagrams_url": urls,
        "stats": {
            "actors": len(actor_set),
            "usecases": len(usecase_map),
            "edges": len(edges),
        },
    }
