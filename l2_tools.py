import os 
from dotenv import load_dotenv
import httpx
import json

load_dotenv()

BASE_URL = os.environ["LLM_BASE_URL"]
API_KEY = os.environ["LLM_API_KEY"]
MODEL = os.environ["LLM_MODEL"]

client = httpx.Client(base_url=BASE_URL, timeout=60, trust_env=False) # trust_env=False：别走系统代理，直连

HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def chat(messages: list[dict], tools:list[dict]) -> dict:
    body = {"model":MODEL, "messages":messages}
    if tools:
        body["tools"] = tools
    resp = client.post("/chat/completions", headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()

# data = chat([{"role": "user", "content": "用一句话介绍 RAG"}])
# print(json.dumps(data, ensure_ascii=False, indent=2)) 


# 1. 写两个工具和它们的 schema
from datetime import datetime

def get_time() -> str:
    """返回当前时间，格式 2026-10-22 21:30:05"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def add(a: int, b: int) -> int:
    return a + b

TOOLS = {"get_time": get_time, "add": add}

TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "get_time",
        "description": "返回当前时间，格式 2026-10-22 21:30:05",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "add",
        "description": "计算两整数想加",
        "parameters": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    }},
]

# 2. 发一次带 tools 的请求，看模型怎么要

# messages = [{"role": "user", "content": "现在几点，另外 17 加 25 等于多少"}]
# data = chat(messages, tools=TOOLS_SCHEMA)
# msg = data["choices"][0]["message"]
# print(data["choices"][0]["finish_reason"])
# print(json.dumps(msg.get("tool_calls"), ensure_ascii=False, indent=2))

# 3 执行、回传、再发，直到 stop

messages = [{"role": "user", "content": "现在几点，另外 17 加 25 等于多少"}]

for round_no in range(5):
    try:
        data = chat(messages, tools=TOOLS_SCHEMA)
        choice = data["choices"][0]
        msg = choice["message"]
        messages.append(msg)                                 # 规则 1，不管要不要工具都放回

        if choice["finish_reason"] != "tool_calls":
            print("最终回答：", msg["content"])
            break

        for call in msg["tool_calls"]:
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])
            try:
                result = TOOLS[name](**args)
            except Exception as e:
                result = f"工具出错：{e}"
            print(f"  调用 {name}({args}) -> {result}")
            messages.append({                                # 规则 2
                "role": "tool",
                "tool_call_id": call["id"],
                "content": str(result),
            })
    except httpx.HTTPStatusError as e: print(e.response.text)


# 4 故意弄坏两次，记下报错原文