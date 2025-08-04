from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["multisource_db"]

case_study_collection = db["case_studies"]
apps_collection = db["apps"]
reviews_collection = db["reviews"]
news_collection = db["news"]
x_twitter_collection = db["x_twitter_collection"]
