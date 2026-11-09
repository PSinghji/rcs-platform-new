import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_NAME = os.getenv("APP_NAME")
    ENV = os.getenv("ENV")

    JWT_SECRET = os.getenv("JWT_SECRET")
    JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES"))

    MONGO_URI = os.getenv("MONGO_URI")
    MONGO_DB = os.getenv("MONGO_DB")

    REDIS_HOST = os.getenv("REDIS_HOST")
    REDIS_PORT = int(os.getenv("REDIS_PORT"))

    JIO_BASE_URL = os.getenv("JIO_BASE_URL")

settings = Settings()

