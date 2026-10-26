# llm.py
import json
import os
from typing import Iterator

import httpx
from dotenv import load_dotenv

from breaker import llm_breaker

load_dotenv()

BASE_URL = os.environ["LLM_BASE_URL"]
API_KEY = os.environ["LLM_API_KEY"]
MODEL = os.environ["LLM_MODEL"]
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", 60))
TUTOR_TIMEOUT = float(os.environ.get("TUTOR_TIMEOUT", 20))

client = httpx.Client(base_url=BASE_URL, timeout=LLM_TIMEOUT, trust_env=False)
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def _post(body: dict) -> dict:
    resp = client.post("/chat/completions", headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()


def chat(messages: list[dict], tools: list[dict] | None = None, tool_choice: dict | None = None) -> dict:
    """发一次请求，返回整个响应 json。熔断中直接抛 CircuitOpen，不发请求。"""
    body = {"model": MODEL, "messages": messages}
    if tools:
        body["tools"] = tools
    if tool_choice:
        body["tool_choice"] = tool_choice
    return llm_breaker.call(lambda: _post(body))


def _chat_stream_raw(messages: list[dict], *, timeout: float) -> Iterator[dict]:
    body = {"model": MODEL, "messages": messages, "stream": True,
            "stream_options": {"include_usage": True}}
    with client.stream("POST", "/chat/completions", headers=HEADERS, json=body, timeout=timeout) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[len("data: "):]
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            if chunk.get("usage"):
                yield {"text": "", "usage": chunk["usage"]}
                continue
            delta = chunk["choices"][0]["delta"].get("content")
            if delta:
                yield {"text": delta}


def chat_stream(messages: list[dict], *, timeout: float = TUTOR_TIMEOUT) -> Iterator[dict]:
    """流式发一次请求，逐片产出 {"text": ...}；最后一片是 {"text": "", "usage": {...}}。
    熔断器包在外面：拿到第一片算成功，第一片之前出错算失败。"""
    yield from llm_breaker.stream(_chat_stream_raw(messages, timeout=timeout))
