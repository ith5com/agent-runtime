import hmac
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel

from log import setup_logging
from runs import init_db, new_trace_id

load_dotenv()
setup_logging()
log = logging.getLogger("agent-runtime")

INTERNAL_TOKEN = os.environ["INTERNAL_TOKEN"]

app = FastAPI(title="agent-runtime")
init_db()


@app.get("/health")
def health():
    return {"ok": True}


def require_internal(token: str) -> None:
    """内部接口鉴权：只认共享密钥。"""
    if not hmac.compare_digest(token, INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="bad internal token")


class CompleteIn(BaseModel):
    status: str
    result: dict | None = None
    run_id: int = 0
    error: str = ""


@app.post("/fake-go/jobs/{job_id}/complete")
def fake_go_complete(job_id: int, body: CompleteIn, x_tenant_id: int = Header(), x_trace_id: str = Header()):
    """假装自己是 Go：把回调收到的东西打进日志。"""
    log.info("fake_go.complete", extra={"job_id":job_id,"tenant_id":x_tenant_id,"trace_id":x_trace_id,"status":body.status,"run_id":body.run_id,"error":body.error})     # job_id、tenant_id、trace_id、status、run_id、error，
                                                   # result 只记题数不记全文，太长
    return {"ok": True}

from typing import Callable
import gateway
from l6_struct import make_quiz


def job_worker(agent_name: str, fn: Callable, job_id: int, tenant_id: int, trace_id: str) -> None:
    """通用后台 worker：设租户，跑 fn，成功失败都回调；回调失败只记日志。fn 无参，返回 (pydantic 结果, Run)。"""
    gateway.current_tenant.set(tenant_id)
    try:
        result, run = fn()
    except Exception as e:
        log.exception(f"{agent_name}.failed", extra={"job_id": job_id, "trace_id": trace_id})
        status, kwargs = "failed", {"error": repr(e)[:500]}
    else:
        log.info(f"{agent_name}.done", extra={"job_id": job_id, "run_id": run.id, "trace_id": trace_id})
        status, kwargs = "done", {"result": result.model_dump(), "run_id": run.id}
    try:
        gateway.complete_job(job_id, status=status, trace_id=trace_id, **kwargs)
    except Exception:
        log.exception(f"{agent_name}.callback_failed", extra={"job_id": job_id, "trace_id": trace_id})



class QuizRunIn(BaseModel):
    job_id: int
    text: str


@app.post("/agents/quiz/run", status_code=202)
def run_quiz(body: QuizRunIn, background: BackgroundTasks,
             x_internal_token: str = Header(), x_tenant_id: int = Header(),
             x_trace_id: str | None = Header(default=None)):
    require_internal(x_internal_token)
    trace_id = x_trace_id or new_trace_id()
    background.add_task(job_worker, "quiz", lambda: make_quiz(body.text, trace_id=trace_id),
                        body.job_id, x_tenant_id, trace_id)
    log.info("quiz.accepted", extra={"job_id": body.job_id, "tenant_id": x_tenant_id, "trace_id": trace_id})
    return {"trace_id": trace_id}

import json
from fastapi.responses import StreamingResponse
from starlette.concurrency import iterate_in_threadpool
from stream import answer_stream


def sse(ev: dict) -> str:
    """一个事件字典 → 一段 SSE 文本：event 行 + data 行 + 空行。"""
    name = ev.get("event", "message")
    data = {k: v for k, v in ev.items() if k != "event"}
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                                          # f-string 拼三行，data 用 json.dumps(ensure_ascii=False)


class AskIn(BaseModel):
    question: str


@app.post("/agents/tutor/stream")
def tutor_stream(body: AskIn, x_internal_token: str = Header(), x_tenant_id: int = Header(),
                 x_trace_id: str | None = Header(default=None)):
    require_internal(x_internal_token)
    q = body.question.strip()
    if not q or len(q) > 500:
        raise HTTPException(status_code=400, detail="question must be 1-500 chars")
    trace_id = x_trace_id or new_trace_id()
    gateway.current_tenant.set(x_tenant_id)
    gen = answer_stream(q, trace_id=trace_id)

    async def events():
        try:
            async for ev in iterate_in_threadpool(gen):
                yield sse(ev)
        finally:
            gen.close()

    log.info("tutor.stream", extra={"tenant_id": x_tenant_id, "trace_id": trace_id})
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})