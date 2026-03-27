import copy
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from config import SmartRouterConfig
from policies import Policy, get_policy_config
from worker import BasicWorker, DPAwareWorker, Worker, WorkerRegistry, WorkerType

from .base import Router

logger = logging.getLogger(__name__)


class VllmPdRouter(Router):
    def __init__(self, config: SmartRouterConfig):
        self.config: SmartRouterConfig = config
        self.worker_registry: WorkerRegistry = WorkerRegistry()
        self.prefill_policy: Policy = get_policy_config(config.prefill_policy_config)
        self.decode_policy: Policy = get_policy_config(config.decode_policy_config)

        # Shared async HTTP client for forwarding requests.
        self.http_client = httpx.AsyncClient(timeout=60 * 60.0)

        # Initialize prefill workers.
        for url in config.prefill_urls:
            if config.prefill_intra_dp_size > 1:
                for rank in range(config.prefill_intra_dp_size):
                    worker = DPAwareWorker(
                        url,
                        WorkerType.PREFILL,
                        config,
                        rank,
                        config.prefill_intra_dp_size,
                    )
                    self.worker_registry.register(worker)
            else:
                worker = BasicWorker(url, WorkerType.PREFILL, config)
                self.worker_registry.register(worker)

        # Initialize decode workers.
        for url in config.decode_urls:
            if config.decode_intra_dp_size > 1:
                for rank in range(config.decode_intra_dp_size):
                    worker = DPAwareWorker(
                        url,
                        WorkerType.DECODE,
                        config,
                        rank,
                        config.decode_intra_dp_size,
                    )
                    self.worker_registry.register(worker)
            else:
                worker = BasicWorker(url, WorkerType.DECODE, config)
                self.worker_registry.register(worker)

        logger.info("registered workers: %s", self.worker_registry.get_all_urls())

    
    # The models method will be called to retrieve the list of available models.
    async def models(self, request: Request) -> JSONResponse:
        # TODO: aggregate models from all workers and return the unique set
        return JSONResponse({"models": ["model1", "model2"]})

    async def health(self, request: Request) -> JSONResponse:
        # TODO: aggregate health status from all workers and return overall health
        return JSONResponse({"status": "healthy"})

    async def add_worker(self, request: Request) -> JSONResponse:
        # TODO: need to dpaware, i.e., add dp_rank and dp_size for vLLM workers
        body = await request.json()
        url = body.get("url")
        worker_type_str = body.get("worker_type")

        if not url or not worker_type_str:
            return JSONResponse(
                {"error": "Both 'url' and 'worker_type' are required"},
                status_code=400,
            )

        try:
            worker_type = WorkerType(worker_type_str)
        except ValueError:
            return JSONResponse(
                {"error": f"Invalid worker type: {worker_type_str}"},
                status_code=400,
            )

        worker = BasicWorker(url, worker_type, self.config)
        self.worker_registry.register(worker)
        return JSONResponse(
            {"message": f"Worker {url} of type {worker_type} added successfully"}
        )

    async def remove_worker(self, request: Request) -> JSONResponse:
        worker_id = request.path_params.get("worker_id")
        if worker_id:
            removed_worker = self.worker_registry.remove(worker_id)
            if removed_worker:
                return JSONResponse({"message": f"Worker {worker_id} removed successfully"})
            return JSONResponse({"error": f"Worker {worker_id} not found"}, status_code=404)
        return JSONResponse({"error": "Worker ID is required"}, status_code=400)

    async def get_workers(self, request: Request) -> JSONResponse:
        return JSONResponse([worker for worker in self.worker_registry.get_all()])

    async def completions(self, request: Request) -> Response:
        body = await request.json()
        headers = self._sanitize_headers(request)
        stream = bool(body.get("stream", False))
        request_text = self._extract_request_text(body)
        return await self._handle_pd_request(
            body=body,
            headers=headers,
            request_text=request_text,
            endpoint_path="/v1/completions",
            api_kind="completions",
            stream=stream,
        )

    async def chat_completions(self, request: Request) -> Response:
        body = await request.json()
        headers = self._sanitize_headers(request)
        stream = bool(body.get("stream", False))
        request_text = self._extract_request_text(body)
        return await self._handle_pd_request(
            body=body,
            headers=headers,
            request_text=request_text,
            endpoint_path="/v1/chat/completions",
            api_kind="chat",
            stream=stream,
        )

    async def _handle_pd_request(
        self,
        body: Dict[str, Any],
        headers: Dict[str, str],
        request_text: str,
        endpoint_path: str,
        api_kind: str,
        stream: bool,
    ) -> Response:
        logger.debug(
            "PD request start api_kind=%s stream=%s endpoint=%s",
            api_kind,
            stream,
            endpoint_path,
        )
        if stream:
            return await self._handle_stream_request(
                body=body,
                headers=headers,
                request_text=request_text,
                endpoint_path=endpoint_path,
                api_kind=api_kind,
            )
        return await self._handle_non_stream_request(
            body=body,
            headers=headers,
            request_text=request_text,
            endpoint_path=endpoint_path,
            api_kind=api_kind,
        )

    async def _prepare_pd_context(
        self,
        body: Dict[str, Any],
        headers: Dict[str, str],
        request_text: str,
        endpoint_path: str,
    ) -> Dict[str, Any] | Response:
        prefill_workers = self.worker_registry.get_healthy_by_type(WorkerType.PREFILL)
        prefill: Optional[Worker] = self.prefill_policy.select_worker(
            prefill_workers, request_text=request_text, headers=headers
        )
        if prefill is None:
            return JSONResponse("No available prefill workers", status_code=503)

        decode_workers = self.worker_registry.get_healthy_by_type(WorkerType.DECODE)
        decode: Optional[Worker] = self.decode_policy.select_worker(
            decode_workers, request_text=request_text, headers=headers
        )
        if decode is None:
            return JSONResponse("No available decode workers", status_code=503)

        prefill.increment_load()
        decode.increment_load()

        request_id = self._generate_vllm_request_id(prefill.base_url(), decode.base_url())
        logger.debug(
            "Generated vLLM request id=%s prefill=%s decode=%s",
            request_id,
            prefill.url(),
            decode.url(),
        )

        try:
            prefill_body = self._get_prefill_body(body)
            prefill_headers = self._get_prefill_headers(headers, request_id, prefill.dp_rank())
            logger.debug(
                "Prepared prefill request id=%s body=%s headers=%s",
                request_id,
                prefill_body,
                self._mask_headers_for_log(prefill_headers),
            )
            logger.debug(
                "vLLM Stage1 Prefill start id=%s url=%s endpoint=%s",
                request_id,
                prefill.url(),
                endpoint_path,
            )
            prefill_response = await self.http_client.post(
                prefill.endpoint_url(endpoint_path),
                json=prefill_body,
                headers=prefill_headers,
            )
        finally:
            prefill.decrement_load()
            logger.debug("vLLM Stage1 Prefill finish id=%s", request_id)

        if not prefill_response.is_success:
            decode.decrement_load()
            return await self._build_upstream_error_response("Prefill", prefill_response)

        return {
            "decode": decode,
            "request_id": request_id,
            "prefill_response": prefill_response,
        }

    async def _handle_non_stream_request(
        self,
        body: Dict[str, Any],
        headers: Dict[str, str],
        request_text: str,
        endpoint_path: str,
        api_kind: str,
    ) -> Response:
        _ = api_kind
        context_or_response = await self._prepare_pd_context(
            body=body,
            headers=headers,
            request_text=request_text,
            endpoint_path=endpoint_path,
        )
        if isinstance(context_or_response, Response):
            return context_or_response

        decode: Worker = context_or_response["decode"]
        request_id: str = context_or_response["request_id"]
        prefill_response: httpx.Response = context_or_response["prefill_response"]

        prefill_response_json = prefill_response.json()
        kv_transfer_params = prefill_response_json.get("kv_transfer_params", {})
        logger.debug(
            "vLLM Stage1 Prefill response id=%s status=%s kv_transfer_params=%s",
            request_id,
            prefill_response.status_code,
            "present" if kv_transfer_params else "empty",
        )
        decode_body = copy.deepcopy(body)
        decode_body["kv_transfer_params"] = kv_transfer_params
        decode_headers = self._get_decode_headers(headers, request_id, decode.dp_rank())

        try:
            logger.debug(
                "vLLM Stage2 Decode start id=%s url=%s endpoint=%s mode=non-stream",
                request_id,
                decode.url(),
                endpoint_path,
            )
            decode_response = await self.http_client.post(
                decode.endpoint_url(endpoint_path),
                json=decode_body,
                headers=decode_headers,
            )
        finally:
            decode.decrement_load()
            logger.debug("vLLM Stage2 Decode finish id=%s mode=non-stream", request_id)

        if not decode_response.is_success:
            return await self._build_upstream_error_response("Decode", decode_response)

        logger.debug(
            "vLLM Stage2 Decode response id=%s status=%s mode=non-stream",
            request_id,
            decode_response.status_code,
        )
        return JSONResponse(decode_response.json(), status_code=decode_response.status_code)

    async def _handle_stream_request(
        self,
        body: Dict[str, Any],
        headers: Dict[str, str],
        request_text: str,
        endpoint_path: str,
        api_kind: str,
    ) -> Response:
        context_or_response = await self._prepare_pd_context(
            body=body,
            headers=headers,
            request_text=request_text,
            endpoint_path=endpoint_path,
        )
        if isinstance(context_or_response, Response):
            return context_or_response

        decode: Worker = context_or_response["decode"]
        request_id: str = context_or_response["request_id"]
        prefill_response: httpx.Response = context_or_response["prefill_response"]

        async def stream_response():
            try:
                prefill_response_json = prefill_response.json()

                first_chunk = self._build_prefill_first_token_chunk(
                    api_kind=api_kind,
                    prefill_response_json=prefill_response_json,
                )
                if first_chunk is not None:
                    logger.debug("Prefill first token emitted id=%s", request_id)
                    yield first_chunk
                else:
                    logger.debug("Prefill first token missing id=%s", request_id)

                kv_transfer_params = prefill_response_json.get("kv_transfer_params", {})
                logger.debug(
                    "vLLM Stage1 Prefill response id=%s status=%s kv_transfer_params=%s",
                    request_id,
                    prefill_response.status_code,
                    "present" if kv_transfer_params else "empty",
                )
                decode_body = copy.deepcopy(body)
                decode_body["kv_transfer_params"] = kv_transfer_params
                decode_headers = self._get_decode_headers(headers, request_id, decode.dp_rank())

                logger.debug(
                    "vLLM Stage2 Decode start id=%s url=%s endpoint=%s mode=stream",
                    request_id,
                    decode.url(),
                    endpoint_path,
                )
                async with self.http_client.stream(
                    "POST",
                    decode.endpoint_url(endpoint_path),
                    json=decode_body,
                    headers=decode_headers,
                ) as decode_response_stream:
                    if not decode_response_stream.is_success:
                        error_body = await decode_response_stream.aread()
                        error_text = error_body.decode(errors="replace")
                        logger.error(
                            "vLLM Stage2 Decode response id=%s status=%s mode=stream body=%s",
                            request_id,
                            decode_response_stream.status_code,
                            error_text,
                        )
                        yield (
                            f"data: {json.dumps({'error': f'Decode server error '
                            f'{decode_response_stream.status_code}: {error_text}'})}\n\n"
                        )
                        return

                    skipped_first_non_empty_token = False
                    async for chunk in decode_response_stream.aiter_bytes():
                        if not chunk:
                            continue

                        if not skipped_first_non_empty_token:
                            has_token = self._chunk_has_non_empty_token(chunk, api_kind)
                            if has_token:
                                skipped_first_non_empty_token = True
                                logger.debug("Decode first non-empty token skipped id=%s", request_id)
                                continue

                        yield chunk
            finally:
                decode.decrement_load()
                logger.debug("vLLM Stage2 Decode finish id=%s mode=stream", request_id)

        return StreamingResponse(stream_response(), media_type="text/event-stream")

    async def _build_upstream_error_response(
        self, stage: str, response: httpx.Response
    ) -> JSONResponse:
        error_body = await response.aread()
        error_text = error_body.decode(errors="replace")
        logger.error(
            "%s server error status=%s body=%s",
            stage,
            response.status_code,
            error_text,
        )
        return JSONResponse(
            {
                "error": f"{stage} server error {response.status_code}: {error_text}"
            },
            status_code=500,
        )

    def _sanitize_headers(self, request: Request) -> Dict[str, str]:
        headers = dict(request.headers)
        headers.pop("content-length", None)
        headers.pop("host", None)
        return headers

    def _mask_headers_for_log(self, headers: Dict[str, Any]) -> Dict[str, Any]:
        masked_headers = copy.deepcopy(headers)
        for key in list(masked_headers.keys()):
            if key.lower() in {"authorization", "cookie", "set-cookie", "proxy-authorization"}:
                masked_headers[key] = "***"
        return masked_headers

    def _extract_request_text(self, body: Dict[str, Any]) -> str:
        if "messages" in body:
            return str(body["messages"])
        if "prompt" in body:
            return str(body["prompt"])
        return json.dumps(body, ensure_ascii=False)

    def _build_prefill_first_token_chunk(
        self, api_kind: str, prefill_response_json: Dict[str, Any]
    ) -> Optional[bytes]:
        """Build one SSE chunk from prefill non-streaming response."""
        choices = prefill_response_json.get("choices") or []
        if not choices:
            return None

        first_choice = choices[0] or {}
        if api_kind == "chat":
            message = first_choice.get("message") or {}
            token_text = message.get("content")
            if not token_text:
                return None
            payload = {
                "id": prefill_response_json.get("id", f"prefill-{uuid.uuid4()}"),
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": prefill_response_json.get("model", ""),
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": token_text},
                        "logprobs": None,
                        "finish_reason": None,
                    }
                ],
            }
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")

        token_text = first_choice.get("text")
        if not token_text:
            return None
        payload = {
            "id": prefill_response_json.get("id", f"prefill-{uuid.uuid4()}"),
            "object": "text_completion",
            "created": int(time.time()),
            "model": prefill_response_json.get("model", ""),
            "choices": [
                {
                    "index": 0,
                    "text": token_text,
                    "logprobs": None,
                    "finish_reason": None,
                }
            ],
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")

    def _chunk_has_non_empty_token(self, chunk: bytes, api_kind: str) -> bool:
        try:
            text = chunk.decode("utf-8")
        except Exception:
            return False

        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue

            data_text = line[5:].strip()
            if not data_text or data_text == "[DONE]":
                continue

            try:
                payload = json.loads(data_text)
            except Exception:
                continue

            choices = payload.get("choices") or []
            if not choices:
                continue

            choice = choices[0] or {}
            token_text: Optional[str]
            if api_kind == "chat":
                delta = choice.get("delta") or {}
                token_text = delta.get("content")
                if token_text is None:
                    token_text = choice.get("text")
            else:
                token_text = choice.get("text")
                if token_text is None:
                    delta = choice.get("delta") or {}
                    token_text = delta.get("content")

            if isinstance(token_text, str) and token_text:
                return True

        return False

    def _get_prefill_body(self, body: Dict[str, Any]) -> Dict[str, Any]:
        new_body = copy.deepcopy(body)
        # Prepare prefill request (max_tokens=1 to force prefill-only mode)
        new_body["max_tokens"] = 1
        if new_body.get("min_tokens") is not None:
            new_body["min_tokens"] = 1
        if new_body.get("max_completion_tokens") is not None:
            new_body["max_completion_tokens"] = 1

        # Force non-streaming for prefill to get JSON response with kv_transfer_params
        new_body["stream"] = False
        # Remove stream_options since we're setting stream=false
        if "stream_options" in new_body:
            del new_body["stream_options"]

        new_body["kv_transfer_params"] = {
            "do_remote_decode": True,
            "do_remote_prefill": False,
            "remote_engine_id": None,
            "remote_block_ids": None,
            "remote_host": None,
            "remote_port": None,
        }
        return new_body

    def _get_prefill_headers(self, headers: Dict[str, str], request_id: str, rank: int) -> Dict[str, Any]:
        new_headers = copy.deepcopy(headers)
        new_headers["Content-Type"] = "application/json"
        new_headers["X-Request-Id"] = request_id

        if self.config.prefill_intra_dp_size > 1:
            new_headers["X-data-parallel-rank"] = str(rank)
        return new_headers

    def _get_decode_headers(self, headers: Dict[str, str], request_id: str, rank: int) -> Dict[str, Any]:
        """Prepare headers for decode request, including vLLM-specific headers."""
        new_headers = copy.deepcopy(headers)
        new_headers["Content-Type"] = "application/json"
        new_headers["X-Request-Id"] = request_id
        if self.config.decode_intra_dp_size > 1:
            new_headers["X-data-parallel-rank"] = str(rank)
        return new_headers

    def _generate_vllm_request_id(self, prefill_url: str, decode_url: str) -> str:
        """Generate a unique request ID for vLLM based on prefill and decode addresses."""
        prefill_addr = prefill_url.replace("http://", "").replace("https://", "")
        decode_addr = decode_url.replace("http://", "").replace("https://", "")
        return f"___prefill_addr_{prefill_addr}___decode_addr_{decode_addr}_{uuid.uuid4()}"
