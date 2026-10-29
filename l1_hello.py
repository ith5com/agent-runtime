import os
from dotenv import load_dotenv

import httpx
import json

# 加载环境变量
load_dotenv()

BASE_URL = os.environ["LLM_BASE_URL"]
API_KEY = os.environ["LLM_API_KEY"]
MODEL = os.environ["LLM_MODEL"]

SYSTEM = '你只能输出JSON格式：{"answer":string, confidence:number}不要输出其他文字'


def step1():
    # 打印验证
    print(
        BASE_URL, MODEL, API_KEY[:6]
    )  # https://api.deepseek.com/v1 deepseek-chat sk-0dc


# 封装请求函数
client = httpx.Client(base_url=BASE_URL, timeout=60, trust_env=False)
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:

    body = {"model": MODEL, "messages": messages}
    if tools:
        body["tools"] = tools

    resp = client.post("/chat/completions", headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()


def step2():
    data = chat([{"role": "user", "content": "请你一句话介绍RAG"}])
    print(json.dumps(data, ensure_ascii=False, indent=2))

    # 下面四行你自己写：回答、finish_reason、prompt_tokens、completion_tokens

    print(data["choices"][0]["finish_reason"])
    print(data["usage"]["prompt_tokens"])
    print(data["usage"]["completion_tokens"])


# 让模型输出 JSON，看它听不听话


def step3():
    ok = 0

    for i in range(5):
        data = chat(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": "什么是RAG"},
            ]
        )
        answer = data["choices"][0]["message"]["content"]
        try:
            obj = json.loads(answer)
            ok = ok + 1
            print(obj)
        except json.JSONDecodeError:
            print(f"第{ok}次失败：", answer)
    print(f"成功：{ok}/5次")


# 流式 stream=Ture、

# data: {"choices":[{"delta":{"content":"你好"}}]}

# data: {"choices":[{"delta":{"content":"，我是助手。"}}]}

# data: [DONE]

import time


def chat_stream(messages: list[dict]):
    t0 = time.monotonic()
    first = None
    pieces = []
    with client.stream(
        "POST",
        "/chat/completions",
        headers=HEADERS,
        json={"model": MODEL, "messages": messages, "stream": True},
    ) as resp:
        resp.raise_for_status()
        # 从响应中逐行读取数据
        for line in resp.iter_lines():
            # 只处理以 data:  开头的行
            if not line.startswith("data: "):
                continue  # 空行等其他内容直接跳过，continue 表示进入下一轮循环。
            payload = line[len("data: ") :]  # 去掉开头的 data: ，保留后面的内容
            if payload == "[DONE]":  # [DONE] 是结束标记
                break
            chunk = json.loads(payload)
            #  choices[0]：取第一个候选回答。
            #  delta：这一块响应带来的增量内容。
            #  .get("content")：取文字字段；字段不存在时返回 None。
            delta = chunk["choices"][0]["delta"].get("content")
            if not delta:
                continue
            if first is None:
                first = time.monotonic() - t0  # 记录从 t0 到现在的耗时
            # - end=""：打印后不换行，让各段文字接在一起。
            # - flush=True：立即刷新输出，便于实时看到生成内容。
            print(delta, end="", flush=True)
            pieces.append(delta)  # 把这段文字存进列表
        print()
        print(f"首字 {first:.2f}s，总耗时 {time.monotonic() - t0:.2f}s")
        return "".join(pieces)


# 验证流式
def step4():
    ok = 0
    for i in range(5):
        answer = chat_stream(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": "你是谁"},
            ]
        )
        try:
            obj = json.loads(answer)
            ok = ok + 1
        except json.JSONDecodeError:
            print(f"第{ok}次失败: {answer}")
    print(f"成功 {ok}/5次")


# 这个 if 的意思是"只有直接运行我才跑下面的"
if __name__ == "__main__":
    step1()
