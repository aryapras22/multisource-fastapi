from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os


class Settings(BaseSettings):

    frontend_origin: str = Field(
        alias="FRONTEND_ORIGIN", default="http://localhost:5173"
    )
    queries_generator_webhook: str = Field(
        alias="QUERIES_GENERATOR_WEBHOOK", default="NONE"
    )
    news_api_key: str = Field(alias="NEWS_API_KEY", default="NONE")
    news_api_endpoint: str = Field(alias="NEWS_API_ENDPOINT", default="NONE")
    twitter_x_api_endpoint: str = Field(alias="TWITTER_X_API_ENDPOINT", default="NONE")
    twitter_x_api_key: str = Field(alias="TWITTER_X_API_KEY", default="NONE")

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
