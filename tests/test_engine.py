import asyncio
import os
import time
from multiprocessing import Process

from smart_router.engine.engine_client import EngineClient
from smart_router.engine.engine import Engine, EngineRequest



def test_engine_and_engine_client():
    addr = "tcp://127.0.0.1:5557"

    engine = Engine(addr, "tcp://127.0.0.1:5558")

    async def run_engine():
        await engine.run()

    asyncio.run(run_engine())

if __name__ == "__main__":
    test_engine_and_engine_client()