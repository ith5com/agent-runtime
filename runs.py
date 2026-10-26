import sqlite3

DB_PATH = "runs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id      TEXT NOT NULL,
    agent         TEXT NOT NULL,
    model         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'running',
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost          TEXT NOT NULL DEFAULT '0',
    latency_ms    INTEGER,
    steps         INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at   TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES runs (id),
    seq           INTEGER NOT NULL,
    kind          TEXT,
    name          TEXT,
    input         TEXT,
    output        TEXT,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms    INTEGER,
    error         TEXT,
    UNIQUE (run_id, seq)
);
"""

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


from decimal import Decimal
# 每百万 token 的价格，单位元。查厂商定价页填，调价改这里。
PRICES = {
    "deepseek-chat": (Decimal("2.0"), Decimal("3.0")),   # (输入, 输出)
}

# (输入 token × 输入单价 + 输出 token × 输出单价) / 1_000_000
def cost_of(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    pin, pout = PRICES.get(model, (Decimal(0), Decimal(0)))
    return Decimal((Decimal(input_tokens * pin) + Decimal(output_tokens * pout)) / 1_000_000)


# 三个写入函数
import json
import time
import uuid

def new_trace_id() -> str:
    return uuid.uuid4().hex

def start_run(*, trace_id: str, agent: str, model: str) -> int:
     with connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (trace_id, agent, model) VALUES (?, ?, ?)",
            (trace_id, agent, model),
        )
        return cur.lastrowid

def add_step(run_id: int, seq: int, kind: str, name: str, *,
             input=None, output=None, input_tokens: int = 0, output_tokens: int = 0,
             latency_ms: int | None = None, error: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO steps (run_id, seq, kind, name, input, output, input_tokens, output_tokens, latency_ms, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",     # 十个字段，自己数
            (run_id, seq, kind, name,
             json.dumps(input, ensure_ascii=False, default=str),
             json.dumps(output, ensure_ascii=False, default=str),
             input_tokens, output_tokens, latency_ms, error),
        )


def finish_run(run_id: int, *, status: str, model: str, input_tokens: int, output_tokens: int,
               latency_ms: int, steps: int, error: str | None = None) -> None:
    cost = cost_of(model, input_tokens, output_tokens)
    with connect() as conn:
        conn.execute(
            """UPDATE runs SET status=?, input_tokens=?, output_tokens=?, cost=?,
               latency_ms=?, steps=?, error=?, finished_at=datetime('now') WHERE id=?""",
            (status, input_tokens, output_tokens, str(cost), latency_ms, steps, error, run_id),
        )

# 读取运行一条run
def get_run(run_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        run = dict(row)
        rows = conn.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY seq", (run_id,)).fetchall()
        # run["steps"] = [...]     # 每行 dict(r)，再把 input、output 两个字段 json.loads
        steps = []
        for r in rows:
            step = dict(r)
            step["input"] = json.loads(step["input"])
            step["output"] = json.loads(step["output"])
            steps.append(step)
        run["step_rows"] = steps
    return run


class Run:
    """一次执行的记账本。with tracked_run(...) as run 交出来的就是它。"""

    def __init__(self, run_id: int, model: str):
        self.id = run_id
        self.model = model
        self.seq = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.status = "done"       # 正常退出时写的状态，块里可以改成 aborted

    def add_usage(self, usage: dict) -> dict:
        self.input_tokens += usage.get("prompt_tokens", 0)
        self.output_tokens += usage.get("completion_tokens", 0)
        return usage

    def step(self, kind: str, name: str, *, usage: dict | None = None,
             input=None, output=None, latency_ms: int | None = None, error: str | None = None) -> int:
        self.seq += 1
        usage = usage or {}
        add_step(self.id, self.seq, kind, name,
                 input=input, output=output,
                 input_tokens=usage.get("prompt_tokens", 0),
                 output_tokens=usage.get("completion_tokens", 0),
                 latency_ms=latency_ms, error=error)
        return self.seq

import time
from contextlib import contextmanager


@contextmanager
def tracked_run(*, trace_id: str | None = None, agent: str, model: str):
    run = Run(start_run(trace_id=trace_id or new_trace_id(), agent=agent, model=model), model)
    t0 = time.perf_counter()
    try:
        yield run
    except Exception as e:
        finish_run(run.id, status="failed", model=model,
                   input_tokens=run.input_tokens, output_tokens=run.output_tokens,
                   latency_ms=int((time.perf_counter() - t0) * 1000), steps=run.seq, error=repr(e))
        raise
    else:
       finish_run(run.id, status=run.status, model=model, # status 用 run.status，其余和上面一样，没有 error
                    input_tokens=run.input_tokens, output_tokens=run.output_tokens,
                    latency_ms=int((time.perf_counter() - t0) * 1000), steps=run.seq)        


STALE_AFTER_MIN = 30


def reap_stale(max_age_min: int = STALE_AFTER_MIN) -> list[int]:
    """把卡在 running 超过 max_age_min 分钟的 run 标成 failed，返回收掉的 id。"""
    err = f"stale: 超过 {max_age_min} 分钟没有结束，进程可能中途退出"
    with connect() as conn:
        rows = conn.execute(
            """UPDATE runs SET status='failed', error=?, finished_at=datetime('now')
               WHERE status='running' AND created_at < datetime('now', ?)
               RETURNING id""",
            (err, f"-{max_age_min} minutes"),
        ).fetchall()
        return [r["id"] for r in rows]