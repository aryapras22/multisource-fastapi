from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os


class Settings(BaseSettings):

    frontend_origin: str = Field(
        alias="FRONTEND_ORIGIN", default="http://localhost:3000"
    )
    queries_generator_webhook: str = Field(
        alias="QUERIES_GENERATOR_WEBHOOK", default="NONE"
    )

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
