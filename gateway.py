import os
from contextvars import ContextVar

import httpx
from dotenv import load_dotenv

load_dotenv()

# 当前请求的租户，由入口处设置，工具里只读。模型永远碰不到它。
current_tenant: ContextVar[int] = ContextVar("current_tenant")

_client = httpx.Client(
    base_url=os.environ["API_BASE_URL"],
    headers={"X-Internal-Token": os.environ["INTERNAL_TOKEN"]},
    timeout=10,
    trust_env=False,
)


def complete_job(job_id: int, *, status: str, trace_id: str,
                 result: dict | None = None, run_id: int = 0, error: str = "") -> None:
    """把任务结果回写给 Go。status 是 done 或 failed。"""
    resp = _client.post(
        f"/fake-go/jobs/{job_id}/complete",
        json={"status":status, "result": result, "run_id": run_id, "error": error},                                    # 四个字段，对着 7.2 的 CompleteIn 填
        headers={"X-Tenant-Id": str(current_tenant.get()), "X-Trace-Id": trace_id},
    )
    resp.raise_for_status()