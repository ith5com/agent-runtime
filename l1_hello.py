# 1. 打印环境变量

import os 
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ["LLM_BASE_URL"]
API_KEY = os.environ["LLM_API_KEY"]
MODEL = os.environ["LLM_MODEL"]

print(BASE_URL, MODEL, API_KEY[:6]) # https://api.deepseek.com/v1 deepseek-chat sk-0dc


# 2. 发第一个请求

import httpx
import json

client = httpx.Client(base_url=BASE_URL, timeout=60, trust_env=False) # trust_env=False：别走系统代理，直连

HEADERS = {"Authorization": f"Bearer {API_KEY}"}

## 封装对话函数
# def chat(messages: list[dict]) -> dict:
#     resp = client.post("/chat/completions", headers=HEADERS, 
#                        json={"model":MODEL, "messages":messages})
#     resp.raise_for_status()
#     return resp.json()

# data = chat([{"role": "user", "content": "用一句话介绍 RAG"}])
# print(json.dumps(data, ensure_ascii=False, indent=2)) 

# print(f"回答：{data['choices'][0]['message']['content']}")
# print(f"finish_reason：{data['choices'][0]['finish_reason']}")
# print(f"prompt_tokens：{data['usage']['prompt_tokens']}")
# print(f"completion_tokens：{data['usage']['completion_tokens']}")、


# 3.让模型输出 JSON，看它听不听话

# SYSTEM = '你只能输出 JSON，格式 {"answer": string, "confidence": number}，不要输出其他任何文字。'
# ok = 0

# for i in range(5):
#     data = chat([
#         {"role": "system", "content": SYSTEM},
#         {"role": "user", "content": "用一句话介绍 RAG"}
#     ])
#     text = data["choices"][0]["message"]["content"]
#     try:
#         obj = json.loads(text)
#         ok = ok + 1
#         print(obj["answer"])
#     except json.JSONDecodeError:
#         printpp(f"第{i}次失败 {text}")
# print(f"{ok}/5 success")


# 4.流式

# import time
# def chat_stream(messages: list[dict]):
#     t0 = time.monotonic()
#     first = None
#     with client.stream("POST", "/chat/completions", headers=HEADERS,
#                        json={"model": MODEL, "messages":messages, "stream":True}) as resp:
#         resp.raise_for_status()
#         for line in resp.iter_lines():
#             if not line.startswith("data: "):
#                 continue
#             payload = line[len("data: "):]
#             if payload == "[DONE]":
#                 break
#             chunk = json.loads(payload)
#             delta = chunk["choices"][0]["delta"].get("content")
#             if not delta:
#                 continue
#             if first is None:
#                 first = time.monotonic() - t0
#             print(delta, end="", flush=True)
#     print()
#     print(f"首字 {first:.2f}s，总耗时 {time.monotonic() - t0:.2f}s")

# chat_stream([
#         {"role": "system", "content": SYSTEM},
#         {"role": "user", "content": "用一句话介绍 RAG"}
#     ])