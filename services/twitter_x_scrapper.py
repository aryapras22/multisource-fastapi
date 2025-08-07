import requests
from config import settings


API_ENDPOINT = settings.twitter_x_api_endpoint
API_KEY = settings.twitter_x_api_key


def scrap_twitter_x(query: str, count: int = 10):
    HEADERS = {"X-API-key": API_KEY}
    PARAMS = {"query": query, "queryType": "Top", "count": count}

    try:
        response = requests.get(url=API_ENDPOINT, headers=HEADERS, params=PARAMS)
        response.raise_for_status()

        data = response.json()
        tweets = data.get("tweets", [])

        processed_tweets = []
        for tweet in tweets:
            processed_tweet = {
                "id": tweet.get("id"),
                "url": tweet.get("url"),
                "text": tweet.get("text", ""),
                "retweet_count": tweet.get("retweetCount", 0),
                "reply_count": tweet.get("replyCount", 0),
                "like_count": tweet.get("likeCount", 0),
                "quote_count": tweet.get("quoteCount", 0),
                "created_at": tweet.get("createdAt"),
                "lang": tweet.get("lang"),
                "author": {
                    "username": tweet.get("author", {}).get("userName", ""),
                    "name": tweet.get("author", {}).get("name", ""),
                    "id": tweet.get("author", {}).get("id"),
                    "profile_picture": tweet.get("author", {}).get("profilePicture"),
                    "description": tweet.get("author", {}).get("description"),
                    "location": tweet.get("author", {}).get("location"),
                    "followers": tweet.get("author", {}).get("followers", 0),
                    "following": tweet.get("author", {}).get("following", 0),
                    "is_blue_verified": tweet.get("author", {}).get(
                        "isBlueVerified", False
                    ),
                    "verified_type": tweet.get("author", {}).get("verifiedType"),
                },
                "entities": tweet.get("entities", {}),
            }
            processed_tweets.append(processed_tweet)

        return processed_tweets

    except requests.exceptions.RequestException as e:
        print(f"Error fetching tweets: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []
