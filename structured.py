from pydantic import BaseModel


def pydantic_to_tool(model_class: type[BaseModel]) -> dict:
    schema = model_class.model_json_schema()
    return {
        "type": "function",
        "function": {
            "name": model_class.__name__,
            "description": model_class.__doc__ or f"输出 {model_class.__name__}",
            "parameters": schema,
        },
    }

import json
import time
from pydantic import ValidationError
from runs import Run


def invoke_structured(send, messages: list[dict], schema: type[BaseModel], *,
                      check=None, run: Run, attempts: int = 3):
    tool = pydantic_to_tool(schema)
    choice = {"type": "function", "function": {"name": tool["function"]["name"]}}
    msgs = list(messages)
    err = "没有尝试"
    for attempt in range(1, attempts + 1):
        t1 = time.perf_counter()
        data = send(msgs, tools=[tool], tool_choice=choice)
        msg = data["choices"][0]["message"]
        usage = run.add_usage(data.get("usage") or {})
        latency = int((time.perf_counter() - t1) * 1000)
        msgs.append(msg)                                   # 规则 1
        calls = msg.get("tool_calls") or []

        if not calls:                                      # 没按要求调工具，自由回答了
            err = "没有调用工具，直接输出了文本"
            run.step("llm", run.model, input=msgs[:-1], output=msg, usage=usage, latency_ms=latency, error=err)
            msgs.append({"role": "user", "content": f"不合格：{err}。请调用 {tool['function']['name']} 工具输出。"})
            continue

        obj, err = None, None
        try:
            obj = schema.model_validate(json.loads(calls[0]["function"]["arguments"]))
            problems = check(obj) if check else []
            if problems:
                err = "；".join(problems)
        except json.JSONDecodeError as e:
            err = f"参数不是合法 JSON：{e}"
        except ValidationError as e:
            err = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())

        run.step("llm", run.model, input=msgs[:-1], output=msg, usage=usage, latency_ms=latency, error=err)
        if err is None:
            return obj

        for c in calls:                                    # 规则 2：每个 id 都回
            msgs.append({"role": "tool", "tool_call_id": c["id"],
                         "content": f"不合格：{err}。请修正后重新完整输出。"})
    raise RuntimeError(f"{attempts} 次都不合格，最后一次：{err}")