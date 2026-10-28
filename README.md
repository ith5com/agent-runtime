# agent-runtime

从零手写一个 Agent 运行时，十章，每章一个可运行的文件。不先学框架，先把协议和工程问题自己做一遍，最后一章再换上 LangChain，验证上层一行不改。

配套教程在 **万小课** 每一步都写了做什么、为什么、怎么验证、常见错误。代码骨架给到函数签名和关键行，空的地方自己填，填完跑，对照预期输出。

## 你会做出什么

一个给业务后端内部调用的 Python AI 服务的运行时层：

| 能力 | 文件 | 章 |
|---|---|---|
| 裸 HTTP 调模型，看懂请求和响应 | l1_hello.py, llm.py | 1 |
| 工具调用协议：模型要工具、你执行、结果回填 | l2_tools.py | 2 |
| Agent 循环：两个出口，工具报错回给模型不中断 | l3_agent.py, runtime.py | 3 |
| 记账：每次运行一条 run、每步一条 step，token、成本、耗时落 SQLite | l4_run.py, runs.py | 4 |
| 上下文管理器统一开始与收尾，失败分支也记实际 token | l5_ctx.py | 5 |
| 结构化输出：pydantic 校验加业务检查，不过就把错误列全打回重试 | l6_struct.py, structured.py | 6 |
| 变成服务：FastAPI 后台任务，202 立即返回，完成后回调，内部口令校验，租户走 contextvar，JSON 日志 | main.py, gateway.py, log.py | 7 |
| 流式：SSE 按 meta / delta / done / error 四种事件推，断开记为 aborted 并保留半截 | stream.py | 8 |
| 稳：超时、三态熔断器、卡在 running 的记录定时回收，熔断器带可注入时钟的测试 | breaker.py, test_breaker.py | 9 |
| 换上 LangChain：边界上双向翻译，循环、记账、熔断、服务一个字不动 | llm_lc.py | 10 |

## 跑起来

需要 Python 3.12、[uv](https://docs.astral.sh/uv/)、一个 OpenAI 兼容接口的模型 API（教程用 DeepSeek）。

```bash
git clone <this repo> && cd agent-runtime
uv sync
cp .env.example .env     # 填 LLM_API_KEY
uv run python l1_hello.py        # 第 1 章：一次调用
uv run python l3_agent.py        # 第 3 章：带工具的循环
uv run python l6_struct.py       # 第 6 章：结构化输出与打回
uv run pytest                    # 第 9 章：熔断器测试
uv run uvicorn main:app --reload # 第 7 到 9 章：服务
```

服务起来后：

```bash
curl -s localhost:8000/health
# 后台任务加回调，回调打到本服务自带的 /fake-go
curl -s -X POST localhost:8000/agents/quiz/run \
  -H 'X-Internal-Token: dev' -H 'X-Tenant-Id: 1' -H 'X-Trace-Id: tr1' \
  -H 'content-type: application/json' \
  -d '{"job_id":1,"text":"<一篇几百字的文章>"}'
# 流式问答，模型先吐 [简短] 或 [详细] 标签，服务解析后随 meta 事件下发
curl -N -X POST localhost:8000/agents/tutor/stream \
  -H 'X-Internal-Token: dev' -H 'X-Tenant-Id: 1' \
  -H 'content-type: application/json' \
  -d '{"question":"什么是 RAG"}'
sqlite3 runs.db 'select id,agent,status,cost from runs order by id desc limit 5'
```

## 怎么学

- 按章顺序做，每章先读 **万小课** 对应章节，自己敲，跑出预期输出再看下一章。
- 不要复制代码。骨架里留空的地方就是这一章要学的东西。
- 每章结束用自己的话写几行笔记。作者的在 [docs/学习笔记.md](docs/学习笔记.md)，末尾附两个面试常问的回答：为什么手写不用框架、跑得好好的为什么换 LangChain。

## 设计上的几个取舍

- **工具报错回给模型，不抛异常。** 模型看到错误会换参数再试，抛出去循环就死了。
- **两个出口。** 模型不再要工具、或到最大步数，缺一个都会烧钱。
- **记账在运行时不在 Agent。** Agent 只写提示词、工具、schema 三件，记账、超时、熔断、回收都是运行时的事。
- **结构化输出打回时把错误一次列全。** 一次只报一条，模型会两次栽在同一处。
- **租户走 contextvar，不进工具签名。** 模型传什么参数都越权不了。
- **熔断器的时钟可注入。** 测试不用 sleep，五个用例一秒跑完。
- **换模型客户端写适配器，不改循环。** 上层只认 OpenAI 格式的字典，第 10 章只加一个文件、改六行 import。

## 目录

```
l1_hello.py … l6_struct.py   每章的练习脚本，独立可跑
llm.py / llm_lc.py           模型客户端：httpx 版 / LangChain 版，接口相同
runtime.py                   run_loop、call_tool
runs.py                      SQLite 记账、Run、tracked_run、reap_stale
structured.py                pydantic_to_tool、invoke_structured
breaker.py                   三态熔断器
gateway.py                   租户上下文、回调客户端
log.py                       JSON 日志
stream.py                    流式问答
main.py                      FastAPI 服务
test_breaker.py              熔断器测试
docs/详解.md                 十章手把手教程
docs/学习笔记.md             作者笔记与面试问答
```

## 下一步

这只是运行时。在它之上做具体的 Agent（导读、RAG 问答、智能客服）和评测框架是另一套教程，做完会放出来。

## License

MIT
