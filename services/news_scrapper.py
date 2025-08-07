import requests
from config import settings


# Configuration
API_KEY = settings.news_api_key
URL = settings.news_api_endpoint


def scrap_news(query: str, count: int):
    HEADERS = {"x-api-token": API_KEY, "Content-Type": "application/json"}
    PAYLOAD = {
        "q": query,
        "theme": "Tech",
        "page_size": count,
        "lang": "en",
        "sort_by": "relevancy",
    }
    try:
        response = requests.post(URL, headers=HEADERS, json=PAYLOAD)
        response.raise_for_status()
        return response.json()  # Add parentheses and remove json.dumps
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch articles: {e}")
        return []  # Return empty list on error
