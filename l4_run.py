import time
from llm import chat, MODEL
from runtime import run_loop
from runs import init_db, start_run, finish_run, get_run, new_trace_id
from l3_agent import TOOLS, SCHEMA, send


def run_agent(question: str, *, max_steps: int = 6) -> int:
    run_id = start_run(trace_id=new_trace_id(), agent="l4", model=MODEL)
    t0 = time.perf_counter()
    r = run_loop(send, [{"role": "user", "content": question}], TOOLS,
                 run_id=run_id, model_name=MODEL, max_steps=max_steps)
    finish_run(run_id,
               status="failed" if r.hit_max_steps else "done",
               model=MODEL, input_tokens=r.input_tokens, output_tokens=r.output_tokens,
               latency_ms=int((time.perf_counter() - t0) * 1000), steps=r.steps,
               error="撞到步数上限" if r.hit_max_steps else None)
    return run_id


if __name__ == "__main__":
    init_db()
    rid = run_agent("现在几点，今天天气怎么样，另外 17 加 25 等于多少", max_steps=1)
    run = get_run(rid)
    print(f"run {rid}: status={run['status']} steps={run['steps']} "
          f"tokens={run['input_tokens']}+{run['output_tokens']} cost={run['cost']}")
    for s in run["step_rows"]:
        print(f"  seq {s['seq']} {s['kind']:4} {s['name']:12} tokens={s['input_tokens']}+{s['output_tokens']} "
              f"{s['latency_ms']}ms" + (f"  error={s['error']}" if s['error'] else ""))

    # 下面三行核对，自己写：
    # 1. steps 表里 kind=='llm' 的行数 == run['steps']
    llm_steps = [s for s in run["step_rows"] if s["kind"] == "llm"]
    # 2. 各 llm 步 input_tokens 之和 == run['input_tokens']，output 同理
    assert len(llm_steps) == run["steps"], f"llm 步 {len(llm_steps)} 条，run 记了 {run['steps']}"
    # 3. Decimal(run['cost']) > 0
    total_in = sum(s["input_tokens"] for s in llm_steps)