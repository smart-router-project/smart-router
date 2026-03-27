import asyncio
import httpx
import time
from collections import defaultdict

class MetricsCollector:

    def __init__(self, workers):
        """
        workers = {
            "prefill": ["http://localhost:8001"],
            "decode": ["http://localhost:8002"]
        }
        """
        self.workers = workers
        self.metrics = defaultdict(list)  # 存时间序列

    async def fetch_metrics(self, client, url):
        try:
            resp = await client.get(f"{url}/metrics", timeout=1.0)
            return resp.json()
        except Exception:
            return {"running": -1, "waiting": -1}

    async def collect_once(self):
        async with httpx.AsyncClient() as client:
            tasks = []

            for typ, urls in self.workers.items():
                for u in urls:
                    tasks.append(self.fetch_metrics(client, u))

            results = await asyncio.gather(*tasks)

        ts = time.time()

        idx = 0
        for typ, urls in self.workers.items():
            for u in urls:
                data = results[idx]
                idx += 1

                self.metrics[(typ, u)].append({
                    "ts": ts,
                    "running": data["running"],
                    "waiting": data["waiting"]
                })

    async def run(self, interval=1.0):
        while True:
            await self.collect_once()
            await asyncio.sleep(interval)