import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """每行一个 JSON：时间、级别、logger 名、消息，加上 extra 里的字段。"""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # 注释一：log.info("...", extra={"a": 1}) 里的字段会挂在 record 上，挑出来
        for k, v in record.__dict__.items():
            if k not in _STD_FIELDS and not k.startswith("_"):
                data[k] = v
        # 注释二：log.exception(...) 会带异常栈，放进 exc 字段
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


# 注释三：LogRecord 自带的字段名集合，用一个空 record 算出来，剩下的就是 extra 里的
_STD_FIELDS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "color_message"}


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # uvicorn 自带 handler，清掉让它走 root 的 JSON 格式
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    # httpx 每个请求都打一行 INFO，太吵
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)