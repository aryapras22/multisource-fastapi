import requests
from app_store_web_scraper import AppStoreEntry
from google_play_scraper import Sort, reviews, search
import re


def get_google_play_apps(query: str, limit: int = 10) -> list:
    """Searches for apps on the Google Play Store."""
    query = re.sub(r"\s+", " ", query)
    try:
        apps = search(query, n_hits=limit)
        output_data = [
            {
                "appName": app.get("title"),
                "appId": app.get("appId"),
                "developer": app.get("developer"),
                "ratingScore": app.get("score"),
                "icon": app.get("icon"),
                "url": app.get("url"),
                "app_desc": app.get("description", ""),  # Adding app description
            }
            for app in apps
        ]
        return output_data
    except Exception as e:
        print(f"Failed to retrieve apps for query '{query}'. Error: {str(e)}")
        return []


def get_google_play_reviews(app_id: str, count: int = 10) -> list:
    """Gets reviews for a specific app from the Google Play Store."""
    try:
        result, _ = reviews(app_id, lang="en", sort=Sort.NEWEST, count=count)
        reviews_data = [
            {
                "reviewer": review.get("userName"),
                "rating": review.get("score"),
                "review": review.get("content"),
            }
            for review in result
        ]
        return reviews_data
    except Exception as e:
        print(f"Failed to retrieve reviews for app ID {app_id}. Error: {str(e)}")
        return []


def get_appstore_apps(query: str, country: str = "us", limit: int = 10) -> list:
    """Searches for apps on the Apple App Store."""
    url = "https://itunes.apple.com/search"
    params = {"term": query, "country": country, "entity": "software", "limit": limit}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        apps = [
            {
                "appName": app.get("trackName"),
                "appId": app.get("trackId"),
                "developer": app.get("artistName"),
                "ratingScore": app.get("averageUserRating"),
                "icon": app.get("artworkUrl100"),
                "url": app.get("trackViewUrl"),
                "app_desc": app.get("description", ""),  # Adding app description
            }
            for app in data.get("results", [])
        ]
        return apps
    except requests.exceptions.RequestException as e:
        print(f"Failed to retrieve App Store apps for query '{query}'. Error: {str(e)}")
        return []


def get_appstore_reviews(app_id: str, country: str = "us", count: int = 10) -> list:
    """Gets reviews for a specific app from the Apple App Store."""

    # https://itunes.apple.com/us/rss/customerreviews/page=1/id=6475364482/sortby=mostrecent/json

    page = count / 2

    try:
        store = AppStoreEntry(country=country, app_id=app_id)
        reviews = []

        for review in store.reviews(limit=count):

            reviews.append(
                {
                    "reviewer": review.user_name,
                    "rating": review.rating,
                    "review": review.review,
                }
            )
        return reviews
    except Exception as e:
        print(
            f"Failed to retrieve App Store reviews for app '{app_id}'. Error: {str(e)}"
        )
        return []
