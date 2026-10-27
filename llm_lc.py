# llm_lc.py
"""LangChain 版模型客户端。对外签名和 llm.py 一模一样，上层不知道底下换了。"""
import json
import os
from typing import Iterator

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from breaker import llm_breaker

load_dotenv()

MODEL = os.environ["LLM_MODEL"]
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", 60))
TUTOR_TIMEOUT = float(os.environ.get("TUTOR_TIMEOUT", 20))


def get_model(**kwargs) -> ChatOpenAI:
    """按 .env 配置返回模型对象。换厂商只改 .env。调用方传的同名参数优先。"""
    opts = {"timeout": LLM_TIMEOUT, "max_retries": 0, "stream_usage": True, **kwargs}
    return ChatOpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"],
                      model=MODEL, **opts)


_model = get_model()
_tutor_model = get_model(timeout=TUTOR_TIMEOUT)


def to_lc(messages: list[dict]) -> list:
    """OpenAI 格式的字典 → LangChain 消息对象。四种 role 四个类。"""
    out = []
    for m in messages:
        role = m["role"]
        if role == "system":
            out.append(SystemMessage(m["content"]))
        elif role == "user":
            out.append(HumanMessage(m["content"]))
        elif role == "assistant":
            calls = [{"name": c["function"]["name"],
                      "args": json.loads(c["function"]["arguments"]),
                      "id": c["id"]} for c in m.get("tool_calls") or []]
            out.append(AIMessage(content=m.get("content") or "", tool_calls=calls))
        elif role == "tool":
            out.append(ToolMessage(content=m["content"], tool_call_id=m["tool_call_id"]))
        else:
            raise ValueError(f"未知 role: {role}")
    return out


def from_lc(resp: AIMessage) -> dict:
    """LangChain 的 AIMessage → 上层认的 OpenAI 格式响应字典。"""
    calls = [{"id": c["id"], "type": "function",
              "function": {"name": c["name"], "arguments": json.dumps(c["args"], ensure_ascii=False)}}
             for c in resp.tool_calls]
    calls += [{"id": c["id"], "type": "function",
               "function": {"name": c["name"], "arguments": c["args"] or ""}}
              for c in resp.invalid_tool_calls]              # 不合法 JSON 原样放回，让上层的 json.loads 去抛
    msg = {"role": "assistant", "content": resp.content or None}
    if calls:
        msg["tool_calls"] = calls
    u = resp.usage_metadata or {}
    return {"choices": [{"message": msg}],
            "usage": {"prompt_tokens": u.get("input_tokens", 0), "completion_tokens": u.get("output_tokens", 0)}}


def chat(messages: list[dict], tools: list[dict] | None = None, tool_choice: dict | None = None) -> dict:
    """和 llm.chat 同签名。tools 是 OpenAI 格式的工具描述，bind_tools 直接认。"""
    model = _model
    if tools:
        choice = tool_choice["function"]["name"] if tool_choice else None
        model = model.bind_tools(tools, tool_choice=choice)
    return llm_breaker.call(lambda: from_lc(model.invoke(to_lc(messages))))


def _chat_stream_raw(messages: list[dict]) -> Iterator[dict]:
    for chunk in _tutor_model.stream(to_lc(messages)):
        if chunk.usage_metadata:
            u = chunk.usage_metadata
            yield {"text": "", "usage": {"prompt_tokens": u.get("input_tokens", 0),
                                         "completion_tokens": u.get("output_tokens", 0)}}
            continue
        if chunk.content:
            yield {"text": chunk.content}


def chat_stream(messages: list[dict], *, timeout: float = TUTOR_TIMEOUT) -> Iterator[dict]:
    """和 llm.chat_stream 同签名。timeout 保留只为签名一致，_tutor_model 构造时已定 20 秒。"""
    yield from llm_breaker.stream(_chat_stream_raw(messages))


def chat(messages: list[dict], tools: list[dict] | None = None, tool_choice: dict | None = None) -> dict:
    """和 llm.chat 同签名。tools 是 OpenAI 格式的工具描述，bind_tools 直接认。"""
    model = _model
    if tools:
        choice = tool_choice["function"]["name"] if tool_choice else None
        model = model.bind_tools(tools, tool_choice=choice)
    return llm_breaker.call(lambda: from_lc(model.invoke(to_lc(messages))))


def _chat_stream_raw(messages: list[dict]) -> Iterator[dict]:
    for chunk in _tutor_model.stream(to_lc(messages)):
        if chunk.usage_metadata:
            u = chunk.usage_metadata
            yield {"text": "", "usage": {"prompt_tokens": u.get("input_tokens", 0),
                                         "completion_tokens": u.get("output_tokens", 0)}}
            continue
        if chunk.content:
            yield {"text": chunk.content}


def chat_stream(messages: list[dict], *, timeout: float = TUTOR_TIMEOUT) -> Iterator[dict]:
    yield from llm_breaker.stream(_chat_stream_raw(messages))