
from dataclasses import dataclass, field
import json
import time
from runs import Run

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
    


def run_loop(send, messages, tools, *, run: Run, max_steps=6) -> LoopResult:
    r = LoopResult(messages=list(messages))

    for _ in range(max_steps):
        t1 = time.perf_counter()
        data = send(r.messages)
        latency = int((time.perf_counter() - t1) * 1000)
        msg = data["choices"][0]["message"]
        usage = run.add_usage(data.get("usage") or {})
        r.steps += 1

        run.step("llm", run.model, input=r.messages, output=msg, usage=usage, latency_ms=latency)
        r.messages.append(msg)
        if not msg.get("tool_calls"):
            return r
        for call in msg["tool_calls"]:
            t2 = time.perf_counter()
            text, error = call_tool(tools, call)

            run.step("tool", call["function"]["name"], input=call["function"]["arguments"],
                     output=text, latency_ms=int((time.perf_counter() - t2) * 1000), error=error)
            r.messages.append({"role": "tool", "tool_call_id": call["id"], "content": text})
    r.hit_max_steps = True
    return r