from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from datetime import datetime
from db import db

router = APIRouter()


def analyze_components(stories, method_type):
    """Analyze user story components by source.
    
    Args:
        stories: List of user story documents
        method_type: Type of method used to generate stories (e.g., "rule-based", "ai-generated")
        
    Returns:
        List of analysis results grouped by source
    """
    by_source = {}

    for story in stories:
        # AI stories use 'content_type' field, user stories use 'source' field
        source = story.get("source") or story.get("content_type", "unknown")
        if source not in by_source:
            by_source[source] = {
                "source": source,
                "method": method_type,
                "total_stories": 0,
                "who_analysis": {"unique": set(), "total": 0, "lengths": []},
                "what_analysis": {"unique": set(), "total": 0, "lengths": []},
                "why_analysis": {
                    "unique": set(),
                    "total": 0,
                    "lengths": [],
                    "word_counts": [],
                },
                "completeness": {
                    "complete": 0,
                    "who_filled": 0,
                    "what_filled": 0,
                    "why_filled": 0,
                },
            }

        data = by_source[source]
        data["total_stories"] += 1

        who = story.get("who", "").strip()
        what = story.get("what", "").strip()
        why = story.get("why", "").strip() if story.get("why") else ""

        if who:
            data["who_analysis"]["unique"].add(who.lower())
            data["who_analysis"]["total"] += 1
            data["who_analysis"]["lengths"].append(len(who))
            data["completeness"]["who_filled"] += 1

        if what:
            data["what_analysis"]["unique"].add(what.lower())
            data["what_analysis"]["total"] += 1
            data["what_analysis"]["lengths"].append(len(what))
            data["completeness"]["what_filled"] += 1

        if why:
            data["why_analysis"]["unique"].add(why.lower())
            data["why_analysis"]["total"] += 1
            data["why_analysis"]["lengths"].append(len(why))
            data["why_analysis"]["word_counts"].append(len(why.split()))
            data["completeness"]["why_filled"] += 1

        if who and what and why:
            data["completeness"]["complete"] += 1

    result = []
    for source, data in by_source.items():
        who_lengths = data["who_analysis"]["lengths"]
        what_lengths = data["what_analysis"]["lengths"]
        why_lengths = data["why_analysis"]["lengths"]
        why_words = data["why_analysis"]["word_counts"]

        result.append(
            {
                "source": source,
                "method": method_type,
                "total_stories": data["total_stories"],
                "who_metrics": {
                    "unique_count": len(data["who_analysis"]["unique"]),
                    "filled_count": data["completeness"]["who_filled"],
                    "filled_rate": (
                        (
                            data["completeness"]["who_filled"]
                            / data["total_stories"]
                            * 100
                        )
                        if data["total_stories"] > 0
                        else 0
                    ),
                    "avg_length": (
                        sum(who_lengths) / len(who_lengths) if who_lengths else 0
                    ),
                    "diversity_rate": (
                        (
                            len(data["who_analysis"]["unique"])
                            / data["completeness"]["who_filled"]
                            * 100
                        )
                        if data["completeness"]["who_filled"] > 0
                        else 0
                    ),
                },
                "what_metrics": {
                    "unique_count": len(data["what_analysis"]["unique"]),
                    "filled_count": data["completeness"]["what_filled"],
                    "filled_rate": (
                        (
                            data["completeness"]["what_filled"]
                            / data["total_stories"]
                            * 100
                        )
                        if data["total_stories"] > 0
                        else 0
                    ),
                    "avg_length": (
                        sum(what_lengths) / len(what_lengths) if what_lengths else 0
                    ),
                    "diversity_rate": (
                        (
                            len(data["what_analysis"]["unique"])
                            / data["completeness"]["what_filled"]
                            * 100
                        )
                        if data["completeness"]["what_filled"] > 0
                        else 0
                    ),
                },
                "why_metrics": {
                    "unique_count": len(data["why_analysis"]["unique"]),
                    "filled_count": data["completeness"]["why_filled"],
                    "filled_rate": (
                        (
                            data["completeness"]["why_filled"]
                            / data["total_stories"]
                            * 100
                        )
                        if data["total_stories"] > 0
                        else 0
                    ),
                    "avg_length": (
                        sum(why_lengths) / len(why_lengths) if why_lengths else 0
                    ),
                    "avg_word_count": (
                        sum(why_words) / len(why_words) if why_words else 0
                    ),
                    "diversity_rate": (
                        (
                            len(data["why_analysis"]["unique"])
                            / data["completeness"]["why_filled"]
                            * 100
                        )
                        if data["completeness"]["why_filled"] > 0
                        else 0
                    ),
                },
                "completeness_rate": (
                    (data["completeness"]["complete"] / data["total_stories"] * 100)
                    if data["total_stories"] > 0
                    else 0
                ),
            }
        )

    return result


@router.get("/analytics/projects/overview")
async def get_projects_overview(exclude_projects: Optional[str] = None):
    """Get overview statistics for all projects"""
    try:

        # Parse excluded projects
        excluded_ids = []
        if exclude_projects:
            excluded_ids = exclude_projects.split(",")

        # Build query
        query = {}
        if excluded_ids:
            query["_id"] = {"$nin": excluded_ids}

        projects = list(db.project.find(query))

        # Status distribution
        status_counts = {}
        for project in projects:
            status = project.get("status", "draft")
            status_counts[status] = status_counts.get(status, 0) + 1

        # Data sources usage
        data_sources = {"appStores": 0, "news": 0, "socialMedia": 0}
        for project in projects:
            ds = project.get("dataSources", {})
            if ds.get("appStores"):
                data_sources["appStores"] += 1
            if ds.get("news"):
                data_sources["news"] += 1
            if ds.get("socialMedia"):
                data_sources["socialMedia"] += 1

        return {
            "total_projects": len(projects),
            "status_distribution": status_counts,
            "data_sources_usage": data_sources,
            "projects": [
                {
                    "id": str(p["_id"]),
                    "name": p["name"],
                    "status": p.get("status", "draft"),
                    "created_at": (
                        p.get("created_at").isoformat() if p.get("created_at") else None
                    ),
                }
                for p in projects
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/projects/{project_id}/data-collection")
async def get_project_data_collection_stats(project_id: str):
    """Get data collection statistics for a specific project"""
    try:
        apps_count = db.apps.count_documents({"project_id": project_id})
        reviews_count = db.reviews.count_documents({"project_id": project_id})
        news_count = db.news.count_documents({"project_id": project_id})
        tweets_count = db.tweets.count_documents({"project_id": project_id})

        return {
            "project_id": project_id,
            "apps": apps_count,
            "reviews": reviews_count,
            "news": news_count,
            "tweets": tweets_count,
            "total": apps_count + reviews_count + news_count + tweets_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/data-collection/overview")
async def get_all_data_collection_stats(exclude_projects: Optional[str] = None):
    """Get data collection statistics across all projects"""
    try:
        excluded_ids = []
        if exclude_projects:
            excluded_ids = exclude_projects.split(",")

        query = {}
        if excluded_ids:
            query["project_id"] = {"$nin": excluded_ids}

        projects = list(
            db.project.find({"_id": {"$nin": excluded_ids}} if excluded_ids else {})
        )

        stats_by_project = []
        for project in projects:
            pid = str(project["_id"])
            stats = {
                "project_id": pid,
                "project_name": project["name"],
                "apps": db.apps.count_documents({"project_id": pid}),
                "reviews": db.reviews.count_documents({"project_id": pid}),
                "news": db.news.count_documents({"project_id": pid}),
                "tweets": db.tweets.count_documents({"project_id": pid}),
            }
            stats["total"] = (
                stats["apps"] + stats["reviews"] + stats["news"] + stats["tweets"]
            )
            stats_by_project.append(stats)

        return {
            "projects": stats_by_project,
            "total_apps": sum(s["apps"] for s in stats_by_project),
            "total_reviews": sum(s["reviews"] for s in stats_by_project),
            "total_news": sum(s["news"] for s in stats_by_project),
            "total_tweets": sum(s["tweets"] for s in stats_by_project),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/projects/{project_id}/requirements")
async def get_project_requirements_stats(project_id: str):
    """Get requirements statistics for a specific project"""
    try:
        # User stories by source
        user_stories = list(db.user_stories.find({"project_id": project_id}))

        source_distribution = {}
        similarity_scores = []
        stories_with_insights = 0

        for story in user_stories:
            source = story.get("source", "unknown")
            source_distribution[source] = source_distribution.get(source, 0) + 1
            similarity_scores.append(story.get("similarity_score", 0))
            if story.get("insight"):
                stories_with_insights += 1

        # AI user stories
        ai_stories = list(db.ai_user_stories.find({"project_id": project_id}))

        sentiment_distribution = {}
        confidence_scores = []

        for story in ai_stories:
            sentiment = story.get("sentiment", "neutral")
            sentiment_distribution[sentiment] = (
                sentiment_distribution.get(sentiment, 0) + 1
            )
            confidence_scores.append(story.get("confidence", 0))

        return {
            "project_id": project_id,
            "user_stories": {
                "total": len(user_stories),
                "by_source": source_distribution,
                "with_insights": stories_with_insights,
                "similarity_scores": {
                    "avg": (
                        sum(similarity_scores) / len(similarity_scores)
                        if similarity_scores
                        else 0
                    ),
                    "min": min(similarity_scores) if similarity_scores else 0,
                    "max": max(similarity_scores) if similarity_scores else 0,
                },
            },
            "ai_stories": {
                "total": len(ai_stories),
                "by_sentiment": sentiment_distribution,
                "confidence_scores": {
                    "avg": (
                        sum(confidence_scores) / len(confidence_scores)
                        if confidence_scores
                        else 0
                    ),
                    "min": min(confidence_scores) if confidence_scores else 0,
                    "max": max(confidence_scores) if confidence_scores else 0,
                },
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/requirements/overview")
async def get_all_requirements_stats(exclude_projects: Optional[str] = None):
    """Get requirements statistics across all projects"""
    try:
        excluded_ids = []
        if exclude_projects:
            excluded_ids = exclude_projects.split(",")

        query = {}
        if excluded_ids:
            query["project_id"] = {"$nin": excluded_ids}

        user_stories = list(db.user_stories.find(query))
        ai_stories = list(db.ai_user_stories.find(query))

        # Aggregate by source
        source_distribution = {}
        for story in user_stories:
            source = story.get("source", "unknown")
            source_distribution[source] = source_distribution.get(source, 0) + 1

        # Aggregate by sentiment
        sentiment_distribution = {}
        for story in ai_stories:
            sentiment = story.get("sentiment", "neutral")
            sentiment_distribution[sentiment] = (
                sentiment_distribution.get(sentiment, 0) + 1
            )

        return {
            "total_user_stories": len(user_stories),
            "total_ai_stories": len(ai_stories),
            "source_distribution": source_distribution,
            "sentiment_distribution": sentiment_distribution,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/projects/{project_id}/ratings")
async def get_project_ratings_distribution(project_id: str):
    """Get review ratings distribution for a specific project"""
    try:
        reviews = list(db.reviews.find({"project_id": project_id}))

        rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        total_rating = 0

        for review in reviews:
            rating = review.get("rating", 0)
            # Handle float ratings by rounding
            rating_int = round(float(rating))
            if 1 <= rating_int <= 5:
                rating_distribution[rating_int] += 1
                total_rating += rating

        avg_rating = total_rating / len(reviews) if reviews else 0

        return {
            "project_id": project_id,
            "total_reviews": len(reviews),
            "distribution": rating_distribution,
            "average_rating": avg_rating,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/projects/{project_id}/engagement")
async def get_project_engagement_metrics(project_id: str):
    """Get social media engagement metrics for a specific project"""
    try:
        tweets = list(db.tweets.find({"project_id": project_id}))

        total_retweets = sum(t.get("retweet_count", 0) for t in tweets)
        total_replies = sum(t.get("reply_count", 0) for t in tweets)
        total_likes = sum(t.get("like_count", 0) for t in tweets)
        total_quotes = sum(t.get("quote_count", 0) for t in tweets)

        return {
            "project_id": project_id,
            "total_tweets": len(tweets),
            "engagement": {
                "retweets": total_retweets,
                "replies": total_replies,
                "likes": total_likes,
                "quotes": total_quotes,
                "total": total_retweets + total_replies + total_likes + total_quotes,
            },
            "average_per_tweet": {
                "retweets": total_retweets / len(tweets) if tweets else 0,
                "replies": total_replies / len(tweets) if tweets else 0,
                "likes": total_likes / len(tweets) if tweets else 0,
                "quotes": total_quotes / len(tweets) if tweets else 0,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/projects/{project_id}/nfr")
async def get_project_nfr_analysis(project_id: str):
    """Get NFR (Non-Functional Requirements) analysis for a specific project"""
    try:
        # Get user stories with insights
        user_stories = list(
            db.user_stories.find(
                {"project_id": project_id, "insight": {"$exists": True}}
            )
        )

        # Get AI stories with field insights
        ai_stories = list(
            db.ai_user_stories.find(
                {"project_id": project_id, "field_insight": {"$exists": True}}
            )
        )

        nfr_frequency = {}

        # Aggregate NFRs from user stories
        for story in user_stories:
            insight = story.get("insight", {})
            nfrs = insight.get("nfr", [])
            for nfr in nfrs:
                nfr_frequency[nfr] = nfr_frequency.get(nfr, 0) + 1

        # Aggregate NFRs from AI stories
        for story in ai_stories:
            field_insight = story.get("field_insight", {})
            nfrs = field_insight.get("nfr", [])
            for nfr in nfrs:
                nfr_frequency[nfr] = nfr_frequency.get(nfr, 0) + 1

        # Sort by frequency
        sorted_nfrs = sorted(nfr_frequency.items(), key=lambda x: x[1], reverse=True)

        return {
            "project_id": project_id,
            "total_stories_with_nfr": len(user_stories) + len(ai_stories),
            "nfr_frequency": dict(sorted_nfrs[:20]),  # Top 20
            "unique_nfrs": len(nfr_frequency),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/projects/{project_id}/clusters")
async def get_project_cluster_stats(project_id: str):
    """Get clustering statistics for a specific project"""
    try:
        # This is a placeholder - actual clustering would need to be computed
        # For now, return basic stats
        user_stories = db.user_stories.count_documents({"project_id": project_id})
        ai_stories = db.ai_user_stories.count_documents({"project_id": project_id})

        return {
            "project_id": project_id,
            "user_stories_count": user_stories,
            "ai_stories_count": ai_stories,
            "message": "Clustering computation required - use clustering API",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/comparison")
async def get_comparison_data(project_ids: str, exclude_projects: Optional[str] = None):
    """Get comparison data for multiple projects"""
    try:
        ids = project_ids.split(",")

        excluded_ids = []
        if exclude_projects:
            excluded_ids = exclude_projects.split(",")
            ids = [pid for pid in ids if pid not in excluded_ids]

        comparison_data = []

        for pid in ids:
            project = db.project.find_one({"_id": pid})
            if not project:
                continue

            data = {
                "project_id": pid,
                "project_name": project["name"],
                "status": project.get("status", "draft"),
                "data_collection": {
                    "apps": db.apps.count_documents({"project_id": pid}),
                    "reviews": db.reviews.count_documents({"project_id": pid}),
                    "news": db.news.count_documents({"project_id": pid}),
                    "tweets": db.tweets.count_documents({"project_id": pid}),
                },
                "requirements": {
                    "user_stories": db.user_stories.count_documents(
                        {"project_id": pid}
                    ),
                    "ai_stories": db.ai_user_stories.count_documents(
                        {"project_id": pid}
                    ),
                },
            }
            comparison_data.append(data)

        return {"projects": comparison_data, "count": len(comparison_data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/sources/detailed")
async def get_detailed_source_analysis(exclude_projects: Optional[str] = None):
    """Get detailed source completeness and quality analysis"""
    try:
        excluded_ids = []
        if exclude_projects:
            excluded_ids = exclude_projects.split(",")

        query = {}
        if excluded_ids:
            query["project_id"] = {"$nin": excluded_ids}

        # Get all user stories
        stories = list(db.user_stories.find(query))

        # Analyze by source
        source_data = {}
        for story in stories:
            source = story.get("source", "unknown")
            if source not in source_data:
                source_data[source] = {
                    "total": 0,
                    "complete": 0,
                    "who_filled": 0,
                    "what_filled": 0,
                    "why_filled": 0,
                    "who_lengths": [],
                    "what_lengths": [],
                    "why_lengths": [],
                    "why_word_counts": [],
                }

            source_data[source]["total"] += 1

            who = story.get("who", "")
            what = story.get("what", "")
            why = story.get("why", "")

            if who:
                source_data[source]["who_filled"] += 1
                source_data[source]["who_lengths"].append(len(who))
            if what:
                source_data[source]["what_filled"] += 1
                source_data[source]["what_lengths"].append(len(what))
            if why:
                source_data[source]["why_filled"] += 1
                source_data[source]["why_lengths"].append(len(why))
                source_data[source]["why_word_counts"].append(len(why.split()))

            if who and what and why:
                source_data[source]["complete"] += 1

        # Calculate statistics
        result = []
        for source, data in source_data.items():
            total = data["total"]
            result.append(
                {
                    "source": source,
                    "total_stories": total,
                    "complete_stories": data["complete"],
                    "completeness_rate": (
                        (data["complete"] / total * 100) if total > 0 else 0
                    ),
                    "who_filled": data["who_filled"],
                    "what_filled": data["what_filled"],
                    "why_filled": data["why_filled"],
                    "avg_who_length": (
                        sum(data["who_lengths"]) / len(data["who_lengths"])
                        if data["who_lengths"]
                        else 0
                    ),
                    "avg_what_length": (
                        sum(data["what_lengths"]) / len(data["what_lengths"])
                        if data["what_lengths"]
                        else 0
                    ),
                    "avg_why_length": (
                        sum(data["why_lengths"]) / len(data["why_lengths"])
                        if data["why_lengths"]
                        else 0
                    ),
                    "avg_why_word_count": (
                        sum(data["why_word_counts"]) / len(data["why_word_counts"])
                        if data["why_word_counts"]
                        else 0
                    ),
                }
            )

        return {
            "sources": result,
            "total_stories": len(stories),
            "overall_completeness": (
                (sum(d["complete"] for d in source_data.values()) / len(stories) * 100)
                if stories
                else 0
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/sources/project-breakdown")
async def get_source_project_breakdown(exclude_projects: Optional[str] = None):
    """Get source distribution breakdown per project"""
    try:
        excluded_ids = []
        if exclude_projects:
            excluded_ids = exclude_projects.split(",")

        projects = list(
            db.project.find({"_id": {"$nin": excluded_ids}} if excluded_ids else {})
        )

        result = []
        for project in projects:
            pid = str(project["_id"])

            # Count stories by source
            stories = list(db.user_stories.find({"project_id": pid}))
            source_counts = {"review": 0, "news": 0, "tweet": 0}

            for story in stories:
                source = story.get("source", "")
                if source in source_counts:
                    source_counts[source] += 1

            result.append(
                {
                    "project_id": pid,
                    "project_name": project["name"],
                    "sources": source_counts,
                    "total": sum(source_counts.values()),
                }
            )

        return {"projects": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/sources/top-personas")
async def get_top_personas(limit: int = 15, exclude_projects: Optional[str] = None):
    """Get most frequent user personas (WHO) across sources"""
    try:
        excluded_ids = []
        if exclude_projects:
            excluded_ids = exclude_projects.split(",")

        query = {}
        if excluded_ids:
            query["project_id"] = {"$nin": excluded_ids}

        stories = list(db.user_stories.find(query))

        # Count personas
        persona_data = {}
        for story in stories:
            who = story.get("who", "").strip().lower()
            if who and len(who) > 0:
                if who not in persona_data:
                    persona_data[who] = {"count": 0, "sources": set()}
                persona_data[who]["count"] += 1
                persona_data[who]["sources"].add(story.get("source", "unknown"))

        # Sort and limit
        sorted_personas = sorted(
            persona_data.items(), key=lambda x: x[1]["count"], reverse=True
        )[:limit]

        result = [
            {"who": persona, "count": data["count"], "sources": list(data["sources"])}
            for persona, data in sorted_personas
        ]

        return {"personas": result, "total_unique": len(persona_data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/sources/top-actions")
async def get_top_actions(limit: int = 20, exclude_projects: Optional[str] = None):
    """Get most frequent actions (WHAT verbs) across sources"""
    try:
        excluded_ids = []
        if exclude_projects:
            excluded_ids = exclude_projects.split(",")

        query = {}
        if excluded_ids:
            query["project_id"] = {"$nin": excluded_ids}

        stories = list(db.user_stories.find(query))

        # Extract action verbs (first word of WHAT)
        action_data = {}
        for story in stories:
            what = story.get("what", "").strip().lower()
            if what:
                # Get first word as action verb
                action = what.split()[0] if what.split() else what
                if action not in action_data:
                    action_data[action] = {"count": 0, "sources": set()}
                action_data[action]["count"] += 1
                action_data[action]["sources"].add(story.get("source", "unknown"))

        # Sort and limit
        sorted_actions = sorted(
            action_data.items(), key=lambda x: x[1]["count"], reverse=True
        )[:limit]

        result = [
            {"action": action, "count": data["count"], "sources": list(data["sources"])}
            for action, data in sorted_actions
        ]

        return {"actions": result, "total_unique": len(action_data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/requirements/comparison")
async def get_requirements_vs_ai_comparison(exclude_projects: Optional[str] = None):
    """Compare user requirements vs AI-generated requirements"""
    try:
        excluded_ids = []
        if exclude_projects:
            excluded_ids = exclude_projects.split(",")

        query = {}
        if excluded_ids:
            query["project_id"] = {"$nin": excluded_ids}

        user_stories = list(db.user_stories.find(query))
        ai_stories = list(db.ai_user_stories.find(query))

        # Count by source for user stories
        user_by_source = {"review": 0, "news": 0, "tweet": 0}
        for story in user_stories:
            source = story.get("source", "")
            if source in user_by_source:
                user_by_source[source] += 1

        # Count by source for AI stories (AI stories use 'content_type' field)
        ai_by_source = {"review": 0, "news": 0, "tweet": 0}
        for story in ai_stories:
            source = story.get("source") or story.get("content_type", "")
            if source in ai_by_source:
                ai_by_source[source] += 1

        # Sentiment analysis for AI stories
        sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
        for story in ai_stories:
            sentiment = story.get("sentiment", "neutral")
            if sentiment in sentiment_counts:
                sentiment_counts[sentiment] += 1

        # Quality comparison - completeness rate
        user_complete = sum(
            1 for s in user_stories if s.get("who") and s.get("what") and s.get("why")
        )
        ai_complete = sum(
            1 for s in ai_stories if s.get("who") and s.get("what") and s.get("why")
        )

        return {
            "user_requirements": {
                "total": len(user_stories),
                "by_source": user_by_source,
                "completeness_rate": (
                    (user_complete / len(user_stories) * 100) if user_stories else 0
                ),
                "complete_count": user_complete,
            },
            "ai_requirements": {
                "total": len(ai_stories),
                "by_source": ai_by_source,
                "sentiment_distribution": sentiment_counts,
                "completeness_rate": (
                    (ai_complete / len(ai_stories) * 100) if ai_stories else 0
                ),
                "complete_count": ai_complete,
            },
            "generation_ratio": {
                "review": (
                    (ai_by_source["review"] / user_by_source["review"])
                    if user_by_source["review"] > 0
                    else 0
                ),
                "news": (
                    (ai_by_source["news"] / user_by_source["news"])
                    if user_by_source["news"] > 0
                    else 0
                ),
                "tweet": (
                    (ai_by_source["tweet"] / user_by_source["tweet"])
                    if user_by_source["tweet"] > 0
                    else 0
                ),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/component-analysis")
async def get_component_analysis(exclude_projects: Optional[str] = None):
    """Analyze WHO/WHAT/WHY components per source and method (rule-based vs AI)"""
    try:
        excluded_ids = []
        if exclude_projects:
            excluded_ids = exclude_projects.split(",")

        query = {}
        if excluded_ids:
            query["project_id"] = {"$nin": excluded_ids}

        user_stories = list(db.user_stories.find(query))
        ai_stories = list(db.ai_user_stories.find(query))

        user_analysis = analyze_components(user_stories, "rule-based")
        ai_analysis = analyze_components(ai_stories, "ai-generated")

        return {
            "rule_based": user_analysis,
            "ai_generated": ai_analysis,
            "summary": {
                "total_rule_based": len(user_stories),
                "total_ai_generated": len(ai_stories),
                "coverage_ratio": (
                    (len(ai_stories) / len(user_stories)) if user_stories else 0
                ),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
