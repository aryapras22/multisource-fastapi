from __future__ import annotations

from typing import List, Dict, Any, Set, Tuple
from collections import defaultdict
import re

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity
from plantuml import PlantUML

from db import user_stories_collection, ai_stories_collection

# Load a pre-trained model for creating sentence embeddings.
# This model is good for semantic similarity tasks.
# The model will be downloaded on the first run.
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# ---- PlantUML Configs ----
PLANTUML_SERVER = "http://www.plantuml.com/plantuml/img/"
_ws_re = re.compile(r"\s+")


def _normalize_key(s: str) -> str:
    """Light normalize for dedup keys: lowercase + collapse spaces + strip quotes/punct at ends."""
    if not s:
        return ""
    s2 = s.strip().strip("\"'()[]{}" "''")
    s2 = _ws_re.sub(" ", s2)
    return s2.lower()


def _alias(prefix: str, idx: int) -> str:
    """Generate short PlantUML-safe aliases."""
    return f"{prefix}{idx}"


def _get_stories_by_project(project_id: str) -> List[Dict[str, Any]]:
    """Fetches all user stories for a given project from the database."""
    cursor = user_stories_collection.find({"project_id": project_id})
    stories = list(cursor)
    # Convert ObjectId to string for JSON serialization
    for story in stories:
        story["_id"] = str(story["_id"])
    return stories


def _vectorize_stories(stories: List[Dict[str, Any]]) -> np.ndarray:
    """
    Converts a list of user stories into numerical vectors.
    The text from 'who', 'what', and 'why' fields are combined to create the embedding.
    """
    # Create a single descriptive sentence for each story
    sentences = [s.get("what", "") for s in stories]

    # Generate embeddings for all sentences
    embeddings = embedding_model.encode(sentences, show_progress_bar=False)
    return embeddings


def cluster_and_summarize_stories(
    project_id: str, distance_threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Main function to fetch, cluster, and summarize user stories for a project.

    1. Fetches stories by project_id.
    2. Converts stories to vector embeddings.
    3. Clusters stories using Agglomerative Clustering based on cosine distance.
    4. For each cluster, finds the most representative story (closest to the centroid).
    5. Returns the clustered data.

    Args:
        project_id: The ID of the project to process.
        distance_threshold: The linkage distance threshold for forming clusters.
                            Ranges from 0 (identical) to 2 (opposite). A value of 0.5
                            is a reasonable starting point for sentence embeddings.

    Returns:
        A dictionary containing the list of clustered user stories.
    """
    stories = _get_stories_by_project(project_id)
    if not stories:
        return {"project_id": project_id, "clusters": []}

    embeddings = _vectorize_stories(stories)

    # Use Agglomerative Clustering. It doesn't require knowing the number of clusters beforehand.
    # We use cosine distance and a distance_threshold to decide cluster membership.
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="cosine",
        linkage="average",
    ).fit(embeddings)

    # Group stories by their assigned cluster label
    clustered_stories = defaultdict(list)
    for i, story in enumerate(stories):
        label = clustering.labels_[i]
        clustered_stories[label].append(story)

    # Process each cluster to find the representative story and summarize
    output_clusters = []
    for label, cluster_items in clustered_stories.items():
        if not cluster_items:
            continue

        # Find the most representative story (centroid) for the cluster
        item_indices = [stories.index(item) for item in cluster_items]
        cluster_embeddings = embeddings[item_indices]

        # Calculate the centroid (mean vector) of the cluster
        centroid = np.mean(cluster_embeddings, axis=0)

        # Find the story closest to the centroid
        similarities = cosine_similarity(cluster_embeddings, centroid.reshape(1, -1))
        representative_idx = np.argmax(similarities)
        representative_story = cluster_items[representative_idx]

        # Collect unique sources within the cluster
        sources = sorted(list({item["source"] for item in cluster_items}))
        for story in cluster_items:
            story.pop("full_sentence", None)
        output_clusters.append(
            {
                "cluster_id": int(label),
                "representative_story": representative_story,
                "stories": cluster_items,
                "size": len(cluster_items),
                "sources": sources,
            }
        )

    # Sort clusters by size (largest first)
    output_clusters.sort(key=lambda x: x["size"], reverse=True)

    # Return only top 10 clusters
    return {"project_id": project_id, "clusters": output_clusters[:10]}


def _get_ai_stories_by_project(project_id: str) -> List[Dict[str, Any]]:
    """Mengambil semua cerita pengguna AI untuk proyek tertentu dari database."""
    cursor = ai_stories_collection.find({"project_id": project_id})
    # ID sudah berupa string (UUID), jadi tidak perlu konversi ObjectId
    return list(cursor)


def _vectorize_ai_stories(stories: List[Dict[str, Any]]) -> np.ndarray:
    """
    Mengonversi daftar cerita pengguna AI menjadi vektor numerik.
    Teks dari field 'what' digunakan untuk membuat embedding.
    """
    sentences = [s.get("what", "") for s in stories]
    embeddings = embedding_model.encode(sentences, show_progress_bar=False)
    return embeddings


def cluster_and_summarize_ai_stories(
    project_id: str, distance_threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Fungsi utama untuk mengambil, mengelompokkan, dan merangkum cerita pengguna AI untuk sebuah proyek.
    """
    stories = _get_ai_stories_by_project(project_id)
    if not stories:
        return {"project_id": project_id, "clusters": []}

    embeddings = _vectorize_ai_stories(stories)

    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="cosine",
        linkage="average",
    ).fit(embeddings)

    clustered_stories = defaultdict(list)
    for i, story in enumerate(stories):
        label = clustering.labels_[i]
        clustered_stories[label].append(story)

    output_clusters = []
    for label, cluster_items in clustered_stories.items():
        if not cluster_items:
            continue

        item_indices = [stories.index(item) for item in cluster_items]
        cluster_embeddings = embeddings[item_indices]
        centroid = np.mean(cluster_embeddings, axis=0)
        similarities = cosine_similarity(cluster_embeddings, centroid.reshape(1, -1))
        representative_idx = np.argmax(similarities)
        representative_story = cluster_items[representative_idx]

        # Gunakan 'content_type' sebagai sumber
        sources = sorted(
            list(
                {
                    item.get("content_type")
                    for item in cluster_items
                    if item.get("content_type")
                }
            )
        )

        output_clusters.append(
            {
                "cluster_id": int(label),
                "representative_story": representative_story,
                "stories": cluster_items,
                "size": len(cluster_items),
                "sources": sources,
            }
        )

    output_clusters.sort(key=lambda x: x["size"], reverse=True)

    # Return only top 10 clusters
    return {"project_id": project_id, "clusters": output_clusters[:10]}


def create_usecase_diagram_from_cluster(
    project_id: str, cluster_id: int, distance_threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Membuat use case diagram dari satu cluster tertentu.
    Menggunakan representative story dari cluster sebagai use case utama.
    """
    # Get the clustering result
    result = cluster_and_summarize_stories(project_id, distance_threshold)

    if not result.get("clusters"):
        return {
            "project_id": project_id,
            "cluster_id": cluster_id,
            "diagrams_puml": [],
            "diagrams_url": [],
            "stats": {"actors": 0, "usecases": 0, "edges": 0},
        }

    # Find the specific cluster
    cluster = None
    for c in result["clusters"]:
        if c["cluster_id"] == cluster_id:
            cluster = c
            break

    if not cluster:
        return {
            "project_id": project_id,
            "cluster_id": cluster_id,
            "diagrams_puml": [],
            "diagrams_url": [],
            "stats": {"actors": 0, "usecases": 0, "edges": 0},
        }

    # Build use case map and edges from cluster stories
    usecase_map: Dict[str, Dict] = {}
    actor_set: Set[str] = set()
    edges: Set[Tuple[str, str]] = set()

    # Add representative story first
    rep_story = cluster["representative_story"]
    rep_who = (rep_story.get("who") or "user").strip()
    rep_what = (rep_story.get("what") or "").strip()
    rep_why = rep_story.get("why") or None

    if rep_what:
        actor_label = _ws_re.sub(" ", rep_who).strip() or "user"
        actor_set.add(actor_label)

        key = _normalize_key(rep_what)
        usecase_map[key] = {
            "label": f"[REPRESENTATIVE] {rep_what}",
            "whys": [rep_why] if rep_why else [],
        }
        edges.add((actor_label, key))

    # Add other stories in the cluster
    for story in cluster["stories"]:
        who = (story.get("who") or "user").strip()
        what = (story.get("what") or "").strip()
        why = story.get("why") or None

        if not what:
            continue

        actor_label = _ws_re.sub(" ", who).strip() or "user"
        actor_set.add(actor_label)

        key = _normalize_key(what)
        if key not in usecase_map:
            usecase_map[key] = {
                "label": what,
                "whys": [],
            }
        if why and why not in usecase_map[key]["whys"]:
            usecase_map[key]["whys"].append(why)

        edges.add((actor_label, key))

    # Build PlantUML diagram
    lines = []
    lines.append("@startuml")
    lines.append("left to right direction")
    lines.append(f"title Cluster {cluster_id} - Use Case Diagram")
    lines.append("")

    # Assign aliases
    actor_alias: Dict[str, str] = {}
    uc_alias: Dict[str, str] = {}
    actor_idx = 1
    uc_idx = 1

    # Actors
    actors_list = sorted(list(actor_set))
    for actor_label in actors_list:
        alias = _alias("A", actor_idx)
        actor_alias[actor_label] = alias
        safe_label = actor_label.replace('"', '\\"').replace("\n", " ")
        lines.append(f'actor "{safe_label}" as {alias}')
        actor_idx += 1

    lines.append("")

    # Use cases
    for uc_key, uc_data in usecase_map.items():
        alias = _alias("U", uc_idx)
        uc_alias[uc_key] = alias
        label = uc_data["label"]
        safe_label = label.replace('"', '\\"').replace("\n", " ")
        lines.append(f'usecase "{safe_label}" as {alias}')
        uc_idx += 1

    lines.append("")

    # Edges
    for actor_label, uc_key in sorted(edges):
        a = actor_alias[actor_label]
        u = uc_alias[uc_key]
        lines.append(f"{a} --> {u}")

    lines.append("@enduml")
    puml = "\n".join(lines)

    # Generate URL
    client = PlantUML(url=PLANTUML_SERVER)
    url = client.get_url(puml)

    return {
        "project_id": project_id,
        "cluster_id": cluster_id,
        "diagrams_puml": [puml],
        "diagrams_url": [url],
        "stats": {
            "actors": len(actor_set),
            "usecases": len(usecase_map),
            "edges": len(edges),
        },
    }


def create_usecase_diagram_from_ai_cluster(
    project_id: str, cluster_id: int, distance_threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Membuat use case diagram dari satu cluster AI stories tertentu.
    Menggunakan representative story dari cluster sebagai use case utama.
    """
    # Get the clustering result
    result = cluster_and_summarize_ai_stories(project_id, distance_threshold)

    if not result.get("clusters"):
        return {
            "project_id": project_id,
            "cluster_id": cluster_id,
            "diagrams_puml": [],
            "diagrams_url": [],
            "stats": {"actors": 0, "usecases": 0, "edges": 0},
        }

    # Find the specific cluster
    cluster = None
    for c in result["clusters"]:
        if c["cluster_id"] == cluster_id:
            cluster = c
            break

    if not cluster:
        return {
            "project_id": project_id,
            "cluster_id": cluster_id,
            "diagrams_puml": [],
            "diagrams_url": [],
            "stats": {"actors": 0, "usecases": 0, "edges": 0},
        }

    # Build use case map and edges from cluster stories
    usecase_map: Dict[str, Dict] = {}
    actor_set: Set[str] = set()
    edges: Set[Tuple[str, str]] = set()

    # Add representative story first
    rep_story = cluster["representative_story"]
    rep_who = (rep_story.get("who") or "user").strip()
    rep_what = (rep_story.get("what") or "").strip()
    rep_why = rep_story.get("why") or None

    if rep_what:
        actor_label = _ws_re.sub(" ", rep_who).strip() or "user"
        actor_set.add(actor_label)

        key = _normalize_key(rep_what)
        usecase_map[key] = {
            "label": f"[REPRESENTATIVE] {rep_what}",
            "whys": [rep_why] if rep_why else [],
        }
        edges.add((actor_label, key))

    # Add other stories in the cluster
    for story in cluster["stories"]:
        who = (story.get("who") or "user").strip()
        what = (story.get("what") or "").strip()
        why = story.get("why") or None

        if not what:
            continue

        actor_label = _ws_re.sub(" ", who).strip() or "user"
        actor_set.add(actor_label)

        key = _normalize_key(what)
        if key not in usecase_map:
            usecase_map[key] = {
                "label": what,
                "whys": [],
            }
        if why and why not in usecase_map[key]["whys"]:
            usecase_map[key]["whys"].append(why)

        edges.add((actor_label, key))

    # Build PlantUML diagram
    lines = []
    lines.append("@startuml")
    lines.append("left to right direction")
    lines.append(f"title AI Cluster {cluster_id} - Use Case Diagram")
    lines.append("")

    # Assign aliases
    actor_alias: Dict[str, str] = {}
    uc_alias: Dict[str, str] = {}
    actor_idx = 1
    uc_idx = 1

    # Actors
    actors_list = sorted(list(actor_set))
    for actor_label in actors_list:
        alias = _alias("A", actor_idx)
        actor_alias[actor_label] = alias
        safe_label = actor_label.replace('"', '\\"').replace("\n", " ")
        lines.append(f'actor "{safe_label}" as {alias}')
        actor_idx += 1

    lines.append("")

    # Use cases
    for uc_key, uc_data in usecase_map.items():
        alias = _alias("U", uc_idx)
        uc_alias[uc_key] = alias
        label = uc_data["label"]
        safe_label = label.replace('"', '\\"').replace("\n", " ")
        lines.append(f'usecase "{safe_label}" as {alias}')
        uc_idx += 1

    lines.append("")

    # Edges
    for actor_label, uc_key in sorted(edges):
        a = actor_alias[actor_label]
        u = uc_alias[uc_key]
        lines.append(f"{a} --> {u}")

    lines.append("@enduml")
    puml = "\n".join(lines)

    # Generate URL
    client = PlantUML(url=PLANTUML_SERVER)
    url = client.get_url(puml)

    return {
        "project_id": project_id,
        "cluster_id": cluster_id,
        "diagrams_puml": [puml],
        "diagrams_url": [url],
        "stats": {
            "actors": len(actor_set),
            "usecases": len(usecase_map),
            "edges": len(edges),
        },
    }


def cluster_and_generate_usecases(
    project_id: str, distance_threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Menggabungkan clustering dan use case diagram generation.
    Generate SATU use case diagram yang berisi 10 representative user stories
    dari top 10 clusters sebagai use cases.

    Returns:
        Dictionary dengan clusters dan SATU use case diagram untuk semua clusters.
    """
    # Get clustering result
    clustering_result = cluster_and_summarize_stories(project_id, distance_threshold)

    if not clustering_result.get("clusters"):
        return {
            "project_id": project_id,
            "clusters": [],
            "usecase_diagram": {
                "diagrams_puml": [],
                "diagrams_url": [],
                "stats": {"actors": 0, "usecases": 0, "edges": 0},
            },
        }

    # Generate single use case diagram from all representative stories
    usecase_map: Dict[str, Dict] = {}
    actor_set: Set[str] = set()
    edges: Set[Tuple[str, str]] = set()

    # Process each cluster's representative story
    for cluster in clustering_result["clusters"]:
        rep_story = cluster["representative_story"]
        rep_who = (rep_story.get("who") or "user").strip()
        rep_what = (rep_story.get("what") or "").strip()
        rep_why = rep_story.get("why") or None

        if rep_what:
            actor_label = _ws_re.sub(" ", rep_who).strip() or "user"
            actor_set.add(actor_label)

            key = _normalize_key(rep_what)
            if key not in usecase_map:
                usecase_map[key] = {
                    "label": rep_what,
                    "whys": [],
                    "cluster_id": cluster["cluster_id"],
                    "cluster_size": cluster["size"],
                }
            if rep_why and rep_why not in usecase_map[key]["whys"]:
                usecase_map[key]["whys"].append(rep_why)

            edges.add((actor_label, key))

    # Build PlantUML diagram
    lines = []
    lines.append("@startuml")
    lines.append("left to right direction")
    lines.append(f"title Use Case Diagram - Top 10 Representative User Stories")
    lines.append("")

    # Assign aliases
    actor_alias: Dict[str, str] = {}
    uc_alias: Dict[str, str] = {}
    actor_idx = 1
    uc_idx = 1

    # Actors
    actors_list = sorted(list(actor_set))
    for actor_label in actors_list:
        alias = _alias("A", actor_idx)
        actor_alias[actor_label] = alias
        # Escape special characters and use : for label with alias
        safe_label = actor_label.replace('"', '\\"').replace("\n", " ")
        lines.append(f'actor "{safe_label}" as {alias}')
        actor_idx += 1

    lines.append("")

    # Use cases with cluster info
    for uc_key, uc_data in usecase_map.items():
        alias = _alias("U", uc_idx)
        uc_alias[uc_key] = alias
        label = uc_data["label"]
        cluster_id = uc_data["cluster_id"]
        cluster_size = uc_data["cluster_size"]
        # Escape special characters in label
        safe_label = label.replace('"', '\\"').replace("\n", " ")
        lines.append(f'usecase "{safe_label}" as {alias}')
        lines.append(
            f"note right of {alias} : Cluster #{cluster_id} ({cluster_size} stories)"
        )
        uc_idx += 1

    lines.append("")

    # Edges
    for actor_label, uc_key in sorted(edges):
        a = actor_alias[actor_label]
        u = uc_alias[uc_key]
        lines.append(f"{a} --> {u}")

    lines.append("@enduml")
    puml = "\n".join(lines)

    # Generate URL
    client = PlantUML(url=PLANTUML_SERVER)
    url = client.get_url(puml)

    usecase_diagram = {
        "diagrams_puml": [puml],
        "diagrams_url": [url],
        "stats": {
            "actors": len(actor_set),
            "usecases": len(usecase_map),
            "edges": len(edges),
            "clusters_represented": len(clustering_result["clusters"]),
        },
    }

    return {
        "project_id": project_id,
        "clusters": clustering_result["clusters"],
        "usecase_diagram": usecase_diagram,
    }


def cluster_and_generate_ai_usecases(
    project_id: str, distance_threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Menggabungkan clustering dan use case diagram generation untuk AI stories.
    Generate SATU use case diagram yang berisi 10 representative AI user stories
    dari top 10 clusters sebagai use cases.

    Returns:
        Dictionary dengan clusters dan SATU use case diagram untuk semua clusters.
    """
    # Get clustering result
    clustering_result = cluster_and_summarize_ai_stories(project_id, distance_threshold)

    if not clustering_result.get("clusters"):
        return {
            "project_id": project_id,
            "clusters": [],
            "usecase_diagram": {
                "diagrams_puml": [],
                "diagrams_url": [],
                "stats": {"actors": 0, "usecases": 0, "edges": 0},
            },
        }

    # Generate single use case diagram from all representative stories
    usecase_map: Dict[str, Dict] = {}
    actor_set: Set[str] = set()
    edges: Set[Tuple[str, str]] = set()

    # Process each cluster's representative story
    for cluster in clustering_result["clusters"]:
        rep_story = cluster["representative_story"]
        rep_who = (rep_story.get("who") or "user").strip()
        rep_what = (rep_story.get("what") or "").strip()
        rep_why = rep_story.get("why") or None

        if rep_what:
            actor_label = _ws_re.sub(" ", rep_who).strip() or "user"
            actor_set.add(actor_label)

            key = _normalize_key(rep_what)
            if key not in usecase_map:
                usecase_map[key] = {
                    "label": rep_what,
                    "whys": [],
                    "cluster_id": cluster["cluster_id"],
                    "cluster_size": cluster["size"],
                }
            if rep_why and rep_why not in usecase_map[key]["whys"]:
                usecase_map[key]["whys"].append(rep_why)

            edges.add((actor_label, key))

    # Build PlantUML diagram
    lines = []
    lines.append("@startuml")
    lines.append("left to right direction")
    lines.append(f"title AI Use Case Diagram - Top 10 Representative User Stories")
    lines.append("")

    # Assign aliases
    actor_alias: Dict[str, str] = {}
    uc_alias: Dict[str, str] = {}
    actor_idx = 1
    uc_idx = 1

    # Actors
    actors_list = sorted(list(actor_set))
    for actor_label in actors_list:
        alias = _alias("A", actor_idx)
        actor_alias[actor_label] = alias
        # Escape special characters and use : for label with alias
        safe_label = actor_label.replace('"', '\\"').replace("\n", " ")
        lines.append(f'actor "{safe_label}" as {alias}')
        actor_idx += 1

    lines.append("")

    # Use cases with cluster info
    for uc_key, uc_data in usecase_map.items():
        alias = _alias("U", uc_idx)
        uc_alias[uc_key] = alias
        label = uc_data["label"]
        cluster_id = uc_data["cluster_id"]
        cluster_size = uc_data["cluster_size"]
        # Escape special characters in label
        safe_label = label.replace('"', '\\"').replace("\n", " ")
        lines.append(f'usecase "{safe_label}" as {alias}')
        lines.append(
            f"note right of {alias} : Cluster #{cluster_id} ({cluster_size} stories)"
        )
        uc_idx += 1

    lines.append("")

    # Edges
    for actor_label, uc_key in sorted(edges):
        a = actor_alias[actor_label]
        u = uc_alias[uc_key]
        lines.append(f"{a} --> {u}")

    lines.append("@enduml")
    puml = "\n".join(lines)

    # Generate URL
    client = PlantUML(url=PLANTUML_SERVER)
    url = client.get_url(puml)

    usecase_diagram = {
        "diagrams_puml": [puml],
        "diagrams_url": [url],
        "stats": {
            "actors": len(actor_set),
            "usecases": len(usecase_map),
            "edges": len(edges),
            "clusters_represented": len(clustering_result["clusters"]),
        },
    }

    return {
        "project_id": project_id,
        "clusters": clustering_result["clusters"],
        "usecase_diagram": usecase_diagram,
    }
