"""FastAPI dependency providers. Routes depend on these, never on concrete infrastructure."""

from fastapi import Request

from app.container import Container


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container
