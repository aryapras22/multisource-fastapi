from __future__ import annotations

from typing import List, Dict, Any
from collections import defaultdict

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

from db import user_stories_collection, ai_stories_collection

# Load a pre-trained model for creating sentence embeddings.
# This model is good for semantic similarity tasks.
# The model will be downloaded on the first run.
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


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

    return {"project_id": project_id, "clusters": output_clusters}


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

    return {"project_id": project_id, "clusters": output_clusters}
