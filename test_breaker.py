# test_breaker.py
import pytest

from breaker import Breaker, CircuitOpen


class Clock:
    """可以手动拨的假时钟：clock.t = 31 就是过了 31 秒。"""
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def boom():
    raise TimeoutError("vendor timeout")


def test_opens_after_fail_max_and_rejects_without_calling():
    clock = Clock()
    b = Breaker("t", fail_max=3, cooldown=30, clock=clock)
    for _ in range(3):
        with pytest.raises(TimeoutError):
            b.call(boom)
    assert b.state == "open"
    called = []
    with pytest.raises(CircuitOpen):
        b.call(lambda: called.append(1))
    assert called == []                                    # 熔断中根本没发请求


def test_half_open_lets_one_probe_and_success_closes():
    clock = Clock()
    b = Breaker("t", fail_max=1, cooldown=30, clock=clock)
    with pytest.raises(TimeoutError):
        b.call(boom)
    clock.t = 31
    assert b.state == "half_open"
    b.before()                                             # 第一个试探放行
    with pytest.raises(CircuitOpen):
        b.before()                                         # 试探还没结果，第二个拒绝
    b.success()
    assert b.state == "closed"


def test_half_open_failure_reopens():
    clock = Clock()
    b = Breaker("t", fail_max=1, cooldown=30, clock=clock)
    with pytest.raises(TimeoutError):
        b.call(boom)
    clock.t = 31
    with pytest.raises(TimeoutError):
        b.call(boom)                                       # 试探失败
    assert b.state == "open"
    clock.t = 40
    assert b.state == "open"                               # 冷却从第二次失败重新计


def test_success_resets_count():
    b = Breaker("t", fail_max=3, cooldown=30, clock=Clock())
    for _ in range(2):
        with pytest.raises(TimeoutError):
            b.call(boom)
    b.call(lambda: "ok")
    for _ in range(2):
        with pytest.raises(TimeoutError):
            b.call(boom)
    assert b.state == "closed"                             # 成功把计数清零了


def test_stream_first_chunk_counts_as_success():
    b = Breaker("t", fail_max=1, cooldown=30, clock=Clock())

    def one_then_fail():
        yield "first"
        raise ConnectionError("mid-stream")

    it = b.stream(one_then_fail())
    assert next(it) == "first"
    with pytest.raises(ConnectionError):
        next(it)
    assert b.state == "closed"                             # 第一片已经到了，中途断不算依赖失败
