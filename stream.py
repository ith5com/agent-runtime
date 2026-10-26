# stream.py
import time
from typing import Iterator

from llm import chat_stream, MODEL
from runs import tracked_run

SYSTEM = "你是读者的学习助教，用中文回答。第一行只写 [简短] 或 [详细] 表示你打算怎么答，换行后再写正文。"
MODE_TAGS = {"[简短]": "brief", "[详细]": "detailed"}


def split_mode(text: str) -> tuple[str, str]:
    """第一行是标签，返回 (mode, 去掉标签的正文)。没标签按 brief。"""
    first, _, rest = text.partition("\n")
    first = first.strip()
    for tag, mode in MODE_TAGS.items():
        if first.startswith(tag):
            return mode, (first[len(tag):] + "\n" + rest).strip()
    return "brief", text.strip()


def answer_stream(question: str, *, trace_id: str | None = None) -> Iterator[dict]:
    """逐事件产出 meta → delta* → done。标签在第一行，攒到看清再发 meta。读者断开时记 aborted。"""
    with tracked_run(trace_id=trace_id, agent="tutor", model=MODEL) as run:
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
        full, head, mode, usage = "", "", None, {}
        t1 = time.perf_counter()
        try:
            for piece in chat_stream(messages):
                if piece.get("usage"):
                    usage = run.add_usage(piece["usage"])
                    continue
                text = piece["text"]
                full += text
                if mode is None:
                    head += text
                    if "\n" not in head and len(head) < 12:
                        continue                          # 标签最长 4 个字，12 字内必见换行
                    mode, rest = split_mode(head)
                    yield {"event": "meta", "run_id": run.id, "mode": mode}
                    if rest:
                        yield {"event": "delta", "text": rest}
                else:
                    yield {"event": "delta", "text": text}
            if mode is None:                              # 回答极短，整段都没到 12 字也没换行
                mode, rest = split_mode(head)
                yield {"event": "meta", "run_id": run.id, "mode": mode}
                if rest:
                    yield {"event": "delta", "text": rest}
        except GeneratorExit:
            run.status = "aborted"
            run.step("llm", run.model, input=messages, output={"content": full, "partial": True},
                     latency_ms=int((time.perf_counter() - t1) * 1000), error="client disconnected")
            return
        run.step("llm", run.model, input=messages, output={"content": full, "mode": mode}, usage=usage,
                 latency_ms=int((time.perf_counter() - t1) * 1000))
        yield {"event": "done", "input_tokens": usage.get("prompt_tokens", 0),
               "output_tokens": usage.get("completion_tokens", 0)}
