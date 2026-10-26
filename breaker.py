import logging
import os
import threading
import time
from collections.abc import Callable, Iterator

log = logging.getLogger(__name__)


class CircuitOpen(Exception):
    """熔断中，请求没有发出去。"""


class Breaker:
    def __init__(self, name: str, fail_max: int, cooldown: float, clock: Callable[[], float] = time.monotonic):
        self.name = name
        self.fail_max = fail_max
        self.cooldown = cooldown
        self._clock = clock
        self._lock = threading.Lock()
        self._fails = 0
        self._opened_at: float | None = None
        self._probing = False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state()

    def _state(self) -> str:
        """closed / open / half_open，从 _opened_at 和时钟算出来，不单独存。调用方必须已持锁。"""
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at < self.cooldown:
            return "open"
        return "half_open"                                               # 距打开不到 cooldown 是 open，否则 half_open

    def before(self) -> None:
        """请求前调用：熔断中就抛 CircuitOpen；半开时只放第一个试探。"""
        with self._lock:
            st = self._state()
            if st == "open" or (st == "half_open" and self._probing):
                raise CircuitOpen(f"{self.name} circuit open")
            if st == "half_open":
                self._probing = True

    def success(self) -> None:
        with self._lock:
            if self._opened_at is not None:
                log.info("breaker.closed", extra={"breaker": self.name})
            self._fails, self._opened_at, self._probing = 0, None, False

    def failure(self) -> None:
        with self._lock:
            self._fails += 1
            self._probing = False
            if self._opened_at is not None or self._fails >= self.fail_max:
                self._opened_at = self._clock()
                log.warning("breaker.open", extra={"breaker": self.name, "fails": self._fails})

    def call(self, fn: Callable):
        """包一次普通调用。"""
        self.before()
        try:
            out = fn()
        except Exception:
            self.failure()
            raise
        self.success()
        return out

    def stream(self, it: Iterator) -> Iterator:
        """包一个流：拿到第一片才算成功；第一片之前出错算失败；中途断开不算依赖失败。"""
        self.before()
        first = True
        try:
            for x in it:
                if first:
                    self.success()
                    first = False
                yield x
        except GeneratorExit:
            raise
        except Exception:
            if first:
                self.failure()
            raise
        if first:                                          # 流是空的也算连通
            self.success()


def _env(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


# 进程内单例，每个依赖一个。多进程部署时各进程独立计数，够用。
llm_breaker = Breaker("llm", fail_max=int(_env("BREAKER_FAIL_MAX", 3)), cooldown=_env("BREAKER_COOLDOWN", 30))