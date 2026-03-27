

from worker import WorkerRegistry, Worker, WorkerType
from config import SmartRouterConfig
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

# The Router class defines the interface for routing requests to different services based on the configuration.
class Router:
    # The chat method will be called for non-streaming requests, 
    # while the chat_stream method will be called for streaming requests.
    async def completions(self, request: Request) -> JSONResponse:
        raise NotImplementedError("Subclasses must implement this method")
    
    # The chat method will be called for non-streaming requests,
    # while the chat_stream method will be called for streaming requests.
    async def chat_completions(self, request: Request) -> StreamingResponse:
        raise NotImplementedError("Subclasses must implement this method")
    
    # The models method will be called to retrieve the list of available models.
    async def models(self, request: Request) -> JSONResponse:
        raise NotImplementedError("Subclasses must implement this method")
    
    async def health(self, request: Request) -> JSONResponse:
        raise NotImplementedError("Subclasses must implement this method")
    
    async def add_worker(self, request: Request) -> JSONResponse:
        raise NotImplementedError("Subclasses must implement this method")
    
    async def remove_worker(self, request: Request) -> JSONResponse:
        raise NotImplementedError("Subclasses must implement this method")
    
    async def get_workers(self, request: Request) -> JSONResponse:
        raise NotImplementedError("Subclasses must implement this method")
    


# The build_router function creates an instance of the appropriate Router subclass
# based on the router_type specified in the configuration.
def build_router(router_config: SmartRouterConfig) -> Router:
    """
    Build a router based on the provided configuration.

    Args:
        router_config (dict): A dictionary containing the router configuration.

    Returns:
        Router: An instance of the Router class configured according to the provided settings.
    """
    if router_config.router_type == "discovery":
        from .service_discovery_router import ServiceDiscoveryRouter
        return ServiceDiscoveryRouter(router_config)
    
    elif router_config.router_type == "vllm-pd-disagg":
        from .vllm_pd_router import VllmPdRouter
        return VllmPdRouter(router_config)
    
    elif router_config.router_type == "sglang-pd-disagg":
        from .sglang_pd_router import SGLangPDRouter
        return SGLangPDRouter(router_config)
    
    else:
        raise ValueError(f"Unsupported router type: {router_config.router_type}")