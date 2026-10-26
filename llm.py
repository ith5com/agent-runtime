import os
import httpx
from dotenv import load_dotenv
import json

load_dotenv()

BASE_URL = os.environ["LLM_BASE_URL"]
API_KEY = os.environ["LLM_API_KEY"]
MODEL = os.environ["LLM_MODEL"]

client = httpx.Client(base_url=BASE_URL, timeout=60, trust_env=False)
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def chat(messages: list[dict], tools: list[dict] | None = None, tool_choice: dict | None = None) -> dict:
    """发一次请求，返回 choices[0] 里的 message。"""
    body = {"model": MODEL, "messages": messages}
    if tools:
        body["tools"] = tools
    if tool_choice:
        body["tool_choice"] = tool_choice
    resp = client.post("/chat/completions", headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()
from typing import Iterator


def chat_stream(messages: list[dict]) -> Iterator[dict]:
    """流式发一次请求，逐片产出 {"text": ...}；最后一片是 {"text": "", "usage": {...}}。"""
    body = {"model": MODEL, "messages": messages, "stream": True,
            "stream_options": {"include_usage": True}}
    with client.stream("POST", "/chat/completions", headers=HEADERS, json=body) as resp:
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
