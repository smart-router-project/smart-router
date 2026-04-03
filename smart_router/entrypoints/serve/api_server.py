import asyncio
import platform
import uvicorn

from multiprocessing import Event, Process

from starlette.applications import Starlette
from starlette.routing import Route

from smart_router.config import build_config, build_parser
from smart_router.engine.engine_client import EngineClient
from smart_router.engine.vllm_engine import start_engine
from smart_router.entrypoints.serve.vllm_routes import VllmRoutes
from smart_router.logger import init_logging

 # 检测操作系统
is_linux = platform.system() == "Linux"

if is_linux:
    # Linux 使用 IPC 协议
    output_addr = "ipc://output.ipc"
    input_addr = "ipc://input.ipc"
else:
    # Windows (或其他) 使用 TCP 协议
    output_addr = "tcp://127.0.0.1:5558"
    input_addr = "tcp://127.0.0.1:5557"

async def startup():
    app.state.engine_client = EngineClient(input_addr, output_addr)
    asyncio.create_task(app.state.engine_client.receive_loop())

async def shutdown():
    app.state.engine_client.shutdown()


vllm_routes = VllmRoutes()

routes = [
    Route("/v1/chat/completions", vllm_routes.chat_completions, methods=["POST"]),
    # Route("/v1/completions", completions, methods=["POST"]),
]

app = Starlette(
    routes=routes,
    on_startup=[startup],
    on_shutdown=[shutdown],
)


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    # build config
    config = build_config(args)

    init_logging(args.log_level)

    # start engine process
    stop_event = Event()
    engine_process = Process(
        target=start_engine,
        args=(config, input_addr, output_addr),
        name="Router Engine",
    )
    engine_process.start()

    uvicorn.run("smart_router.entrypoints.serve.api_server:app", host=args.host, port=args.port, workers=8)
