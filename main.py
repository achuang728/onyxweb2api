"""Onyx to OpenAI API proxy server."""
import json
import logging
import time
import traceback
import uuid
from typing import Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

import config
import onyx

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("onyxtoopenaicodex")

app = FastAPI(title="Onyx2OpenAI", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

http_client: Optional[httpx.AsyncClient] = None


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Global Error: %s\n%s", str(exc), traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"error": {"message": str(exc), "type": "server_error"}},
    )


@app.on_event("startup")
async def startup():
    global http_client
    http_client = httpx.AsyncClient(timeout=float(config.REQUEST_TIMEOUT), trust_env=False)
    logger.info("Server starting on port %s", config.PORT)
    logger.info("Available models: %s", len(config.MODEL_MAP))


@app.on_event("shutdown")
async def shutdown():
    global http_client
    if http_client:
        await http_client.aclose()


def verify_auth(authorization: Optional[str] = None):
    if not config.API_KEY:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization header")
    token = authorization.split(" ", 1)[1]
    if token != config.API_KEY:
        raise HTTPException(401, "Invalid token")


@app.get("/")
async def root():
    return {"message": "Onyx2OpenAI Server is Running!", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "models": len(config.MODEL_MAP)}


@app.get("/v1/models")
async def list_models(authorization: Optional[str] = Header(None)):
    verify_auth(authorization)
    data = [
        {
            "id": model_name,
            "object": "model",
            "created": 1700000000,
            "owned_by": "onyx",
        }
        for model_name in config.MODEL_MAP
    ]
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: Optional[str] = Header(None)):
    verify_auth(authorization)

    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    messages = body.get("messages", [])
    model_name = body.get("model", "claude-opus-4.6")
    stream = body.get("stream", True)
    include_reasoning = body.get("include_reasoning", True)

    logger.info("Request: model=%s, messages=%s, stream=%s", model_name, len(messages), stream)

    if stream:
        return await _stream_response(messages, model_name, include_reasoning)
    return await _non_stream_response(messages, model_name, include_reasoning)


async def _stream_response(messages, model_name, include_reasoning):
    response_id = f"chatcmpl-{uuid.uuid4()}"

    async def generate():
        try:
            async for item_type, content in onyx.stream_chat(http_client, messages, model_name):
                if item_type == "thinking" and include_reasoning:
                    chunk = {
                        "id": response_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_name,
                        "choices": [{
                            "index": 0,
                            "delta": {"reasoning_content": content},
                            "finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                elif item_type == "text":
                    chunk = {
                        "id": response_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_name,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("Stream error: %s", e, exc_info=True)
            err_msg = str(e).replace('"', "'")
            error_event = {"error": {"message": err_msg, "type": "upstream_error"}}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

        end_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model_name,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(end_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def _non_stream_response(messages, model_name, include_reasoning):
    response_id = f"chatcmpl-{uuid.uuid4()}"
    text_content, thinking_content = await onyx.full_chat(http_client, messages, model_name)

    message = {"role": "assistant", "content": text_content}
    if include_reasoning and thinking_content:
        message["reasoning_content"] = thinking_content

    return JSONResponse({
        "id": response_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    })


if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("Onyx2OpenAI Server v1.0")
    print("=" * 50)
    print(f"Address: http://127.0.0.1:{config.PORT}")
    print("Models:  /v1/models")
    print("Chat:    /v1/chat/completions")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
