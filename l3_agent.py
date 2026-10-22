# 4 l3_agent.py：三个工具加一个坏的
from llm import chat
from runtime import run_loop
from l2_tools import get_time, add, TOOLS_SCHEMA


def broken() -> str:
    """查询今天的天气"""
    raise RuntimeError("天气服务挂了")


TOOLS = {"get_time": get_time, "add": add, "broken": broken}
SCHEMA = TOOLS_SCHEMA + [{"type": "function", "function": {
    "name": "broken", "description": "查询今天的天气",
    "parameters": {"type": "object", "properties": {}, "required": []},
}}]


def send(messages):
    return chat(messages, tools=SCHEMA)


if __name__ == "__main__":
    q = [{"role": "user", "content": "现在几点，今天天气怎么样，另外 17 加 25 等于多少"}]
    r = run_loop(send, q, TOOLS, max_steps=6)
    print("steps:", r.steps, "hit_max_steps:", r.hit_max_steps)
    print("最终回答：", r.messages[-1]["content"])