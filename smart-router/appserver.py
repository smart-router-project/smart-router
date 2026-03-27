import logging

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route

from router import Router

# 日志
logger = logging.getLogger(__name__)

async def startup():
    logger.info("Router staring...")


async def shutdown():
    logger.info("Shutting down router")


def build_app(router: Router) -> Starlette:
    """Build the Starlette application with the specified router."""
    routes = [
        Route("/health", router.health, methods=["GET"]),
        Route("/v1/models", router.models, methods=["GET"]),
        Route("/v1/chat/completions", router.chat_completions, methods=["POST"]),
        Route("/v1/completions", router.completions, methods=["POST"]),
        Route("/add_worker", router.add_worker, methods=["POST"]),
        Route("/remove_worker", router.remove_worker, methods=["POST"]),
        Route("/get_worker_urls", router.get_workers, methods=["GET"]),
    ]
    app = Starlette(
        routes=routes,
        on_startup=[startup],
        on_shutdown=[shutdown],
    )
    return app

