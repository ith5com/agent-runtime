import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ["LLM_BASE_URL"]
API_KEY = os.environ["LLM_API_KEY"]
MODEL = os.environ["LLM_MODEL"]

client = httpx.Client(base_url=BASE_URL, timeout=60, trust_env=False)
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """发一次请求，返回 choices[0] 里的 message。"""
    body = {"model": MODEL, "messages": messages}
    if tools:
        body["tools"] = tools
    resp = client.post("/chat/completions", headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()
