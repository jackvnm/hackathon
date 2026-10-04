from fastapi import Request

from app.config import Settings
from app.storage import Store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> Store:
    return request.app.state.store
