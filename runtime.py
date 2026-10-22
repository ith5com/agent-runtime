
from dataclasses import dataclass, field
import json

# 1 LoopResult：循环的返回值

@dataclass
class LoopResult:
    messages: list[dict] = field(default_factory=list)
    steps: int = 0
    hit_max_steps: bool = False


# 2 call_tool：工具出错不抛

def call_tool(tools: dict, call: dict) -> tuple[str, str | None]:
    name = call["function"]["name"]
    if name not in tools:
        msg = f"没有名为 {name} 的工具，可用的有：{', '.join(tools)}"
        return msg, msg
    try:
        args = json.loads(call["function"]["arguments"])
    except json.JSONDecodeError as e:
        # 回给模型"参数不是合法 JSON"，第二个返回值也填上
       
        msg = f"参数不是合法 JSON：{e}"
        return msg, msg        
    try:
        result = tools[name](**args)
        return str(result), None
    except Exception as e:
         # 回给模型"工具暂时不可用"，第二个返回值填 repr(e)
        return "工具暂时不可用", repr(e)

# 3 run_loop 两个出口
def run_loop(send, messages:list[dict], tools:list[dict], *, max_steps: int = 6) -> LoopResult:
    r = LoopResult(messages=list(messages))
    for _ in range(max_steps):
        data = send(r.messages)
        msg = data["choices"][0]["message"]
        r.steps += 1
        # 3.5 打印
        calls = msg.get("tool_calls") or []
        names = ", ".join(c["function"]["name"] + c["function"]["arguments"] for c in calls)
        print(f"step {r.steps} llm -> {names or 'stop'}")
        r.messages.append(msg)                      # 规则 1
        if not msg.get("tool_calls"):
            return r                                # 出口一：正常结束
        for call in msg["tool_calls"]:
           
            text, error = call_tool(tools, call)
            print(f"step {r.steps} tool {call['function']['name']} -> {text}" + (f"  [error: {error}]" if error else "")) # 打印
            r.messages.append({                     # 规则 2
                "role": "tool",
                "tool_call_id": call["id"],
                "content": text,
            })
    r.hit_max_steps = True                          # 出口二：撞上限
    return r