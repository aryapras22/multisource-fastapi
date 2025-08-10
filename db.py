from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["multisource_db"]


# case_study_collection = db["case_studies"]
project_collection = db["project"]
apps_collection = db["apps"]
reviews_collection = db["reviews"]
news_collection = db["news"]
tweets_collection = db["tweets"]
user_stories_collection = db["user_stories"]
