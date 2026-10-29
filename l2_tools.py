# 这一章主要解决的问题：告诉大模型，你有哪些函数。大模型返回调用函数名和参数，无需回答。调用完毕后，再告诉大模型。如此循环，这就是Agent的所有秘密了。
# 流程：
# 0. 发送消息请求，加一个tools字段，是一个JSON Schema描述
# 1. 大模型返回 finish_reason:"tool_calls"
# 2. 根据大模型返回的 choices[0]["message"]["tool_calls"], 的function， 里面调用函数和参数。
# 3. 执行完毕后，发送会给大模型，role:tool, toll_call_id:"", content:""
# 4. 等待大模型返回结果。如果还需要调用，就循环 1-3 的步骤。

from l1_hello import chat
import json
import httpx

# 工具定义
from datetime import datetime

# 在langchain框架下，@tool 会自动生成这个SCHEMA
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {"name": "get_time", "description": "获取当前时间"},
        "parameters": [{"type": "object", "properties": {}, "required": []}],
    },
    {
        "type": "function",
        "function": {
            "name": "add",
            "description": "计算两个数的和",
            "parameters": {
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                "required": ["a", "b"],
            },
        },
    },
]


# 定义函数
def get_time():
    """返回当前时间，格式 2026-10-22 21:30:05"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add(a: int, b: int) -> int:
    return a + b


# 映射
TOOLS = {"get_time": get_time, "add": add}


# 执行一次
def step1():
    data = chat(
        messages=[{"role": "user", "content": "现在几点，另外 17 加 25 等于多少"}],
        tools=TOOLS_SCHEMA,
    )

    msg = data["choices"][0]["message"]

    print(json.dumps(msg.get("tool_calls"), ensure_ascii=False, indent=2))
    print(data["choices"][0]["finish_reason"])
    # print(json.dumps(data, ensure_ascii=False, indent=2))


# 执行，回传，再发，直到STOP
def step2():
    messages = [{"role": "user", "content": "现在几点，另外 17 加 25 等于多少"}]
    try:
        for round_no in range(5):
            data = chat(
                messages,
                tools=TOOLS_SCHEMA,
            )
            choice = data["choices"][0]
            msg = choice["message"]
            messages.append(msg)

            print(f"reason-> {choice['finish_reason']}")

            if choice["finish_reason"] != "tool_calls":
                print(f"最终回答：{msg['content']}")
                break

            for call in msg["tool_calls"]:
                name = call["function"]["name"]
                args = json.loads(call["function"]["arguments"])
                try:
                    # 如果没有JSON SCHME 没有写properties和required， 就不能保证和函数的参数匹配。可能会报错，取决大模型是否猜对。
                    result = TOOLS[name](**args)
                except Exception as e:
                    result = f"工具出错：{e}"

                print(f" 调用 {name}({args}) -> {result}")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": str(result),
                    }
                )
    except httpx.HTTPStatusError as e:
        print(e.response.text)


if __name__ == "__main__":
    step2()
