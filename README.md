# agent-runtime

从零重搭 zhice-ai 运行时的练习场。教程在 ../ai-redo/，代码在这里。规则：

1. 代码我自己敲，Claude 只出题、给提示、批改。
2. 每章结束，用自己的话在下面写 3 到 5 行。
3. zhice-ai/ 是参考答案，卡住超过 20 分钟才去翻。
4. 先用最原始的写法，感到痛了再引入库。

## 学习笔记

### 第 1 章 模型接口就是 HTTP

- 调模型本质就是发一个 POST，body 带 messages 列表，返回答案。
- 返回里认三样：回答、finish_reason、usage 里的提示词 token 和完成 token。
- 让模型只输出 JSON 跑了 5 次成功 5 次。但样本太小，输出复杂的时候还得校验。
- 这一章没卡住。

### 第 2 章 工具调用协议

- 模型"调工具"时它不执行。我的代码拿模型返回的函数名去查工具字典，找到函数执行，把结果作为 tool 消息发回去。
- 两条硬规则：一，模型那条回答不管要不要工具都要原样放回 messages；二，每一个 tool_call 都要有一条对应的 tool 消息，少一条就 400。
- 实验一删掉 schema 里的 b：模型只传了 a，我的代码在执行那行炸了。加 try 把错误回给模型后，它重试一次还是只传 a，两次失败才放弃工具自己算了 42。
- 实验二漏回传一条 tool 消息：第一轮成功，后面四轮都 400，因为 except 没有 break，拿着同一份坏掉的 messages 又发了四次。400 是请求有错，重发没用，该直接停。

### 第 3 章 Agent 循环

- `if __name__ == "__main__":` 下面的代码只在直接运行这个文件时跑，别人 import 时不跑。文件里的函数和字典是工具箱，给别人借用；"跑起来看效果"的代码是演示，全放这个 if 下面。以后每个文件都这么写。
- Python 的默认值只在定义时创建一次，所有实例共用。字段写 `messages: list = []`，a 和 b 两个对象拿到的是同一个列表，a 加一条 b 也多一条。要写 `field(default_factory=list)`，每次新建实例才给一个新的。dataclass 看到 `= []` 会直接报错。
- 这章解决什么问题, 封装llm和工具调用报错处理和agnetloop
- 两个出口怎么区分，规则一：跑到tool没有了，正常。规则二：跑到step循环上限
- 工具错和请求错为什么一个兜一个放，工具是网络调用会失败，抛出去一次超时毁掉整个运行；回给模型它能换办法或说明情况。但 400、401 这种配置错重试也没用，应该抛到最上面让人修。区分标准：这个错换个时间或换个做法会不会好。
### 第 4 章 记账：run 与 step

- 把第 3 章的打印换成写 SQLite，后面能查每次运行发生了什么、能算钱。
- runs 表一次 Agent 请求一条，存状态、总 token、成本、耗时；steps 表存这次请求里每一步做了什么，llm 步记 token，tool 步记错误。
- run 先建再跑：开始就插一条 running，结束再更新。中途进程被杀，这条 running 还在，能发现卡住；等结束再插就什么都没有了。我表里 id 为 1 那条就是这么留下的。
- seq 是 steps 表的行号，llm 和 tool 都数；steps 只数模型调用次数。max_steps=1 那次 steps 是 1，seq 到 4。
- 字典里的键和表的列名撞了会被覆盖：get_run 把列表塞进 run["steps"]，把步数那个数字盖掉了，assert 报错离原因很远。改成 run["step_rows"]。

### 第 5 章 上下文管理器收尾

- 解决什么问题：第 4 章每个 Agent 入口都要抄 start_run、try、finish_run done、except finish_run failed、raise 这十几行，而且 l4 的 run_agent 没有 try，send 一炸记录就停在 running。用 with 包起来，Agent 代码里只剩业务。
- yield 前后：yield 之前是进入（start_run 建 Run 交出去），yield 之后是退出（finish_run）。with 块里的代码在 yield 那一行"里面"跑，块里 raise 会从 yield 冒出来，被 except 接住。
- except 里要 raise：上下文管理器只负责收尾，不负责吞错。吞了上层以为成功。裸 raise 不写 raise e，保留原始调用栈。
- 失败记 0 的 bug 怎么根治：token 和 seq 都挂在 yield 交出去的 Run 对象上，成功和失败两个分支读的是同一个对象，没有第二份数据可以写错。l5 验证里 failed 那条 token 是 371+87。
- 要影响 finish_run 写什么（比如 run.status = "aborted"），必须在 with 块结束之前改，块一结束 else 分支就已经把表写了。

### 第 6 章 结构化输出与打回重试

- 解决什么问题：出题、导读的结果要存库，必须是固定结构的 JSON。让模型"输出 JSON"是在自由文本里写，厂商不保证格式；借工具调用协议，把 Quiz 的 schema 当成一个工具的参数，加 tool_choice 强制它调，arguments 就是按 schema 生成的 JSON。
- 两层校验怎么分：格式层在运行时，pydantic 的 model_validate 统一做，所有 Agent 一样；质量层在 Agent，check_quiz 返回问题列表，运行时只负责调它、拼成 error 发回去。
- 6.4 统计（ARTICLE 还是占位符，没换真文章，数字只能看个形状）：10 次里 8 次一次合格，2 次打回后合格，0 次失败。
- 6.5 改严到 10 题：第一次跑 10 轮全失败，原因是条件改成了 `< 10` 但文案还写"至少 3 题"，模型收到"至少 3 题，现在 4 题"不知道改什么。打回时模型唯一能看到的就是 error 字符串，阈值要提成变量让条件和文案用同一个。改对后 3 轮都是第一次出 2 到 4 题，打回一次补到正好 10 题，第一题题干全变了，是整份重写不是往后追加。
- 占位符 `...` 单独一行能运行，`problems.append(...)` 塞进去的是 Ellipsis 对象，到 join 时才炸；`len(q.answer)` 对 int 用 len 会 TypeError，这次没炸只是模型没出过越界答案。

### 第 7 章 变成服务：后台任务与回调

- 解决什么问题：前六章都是脚本，Go 调不到。这章用 FastAPI 把出题变成常驻服务：收到请求立刻回 202 带 trace_id，BackgroundTasks 在线程池里跑 Agent，跑完 POST 回调。出题要几十秒，HTTP 连接不能挂着等，所以结果靠回调送回去而不是放在响应里。
- 租户为什么放 contextvar：工具参数是模型填的，tenant_id 做参数模型就能填别人的。放 `current_tenant` 里，入口 set、工具 get，工具签名里没有这个参数，模型没有途径碰到。线程池里 contextvar 不保证带过去，worker 第一行要重新 set。没 set 就 get 抛 LookupError，这是故意的，不能默默用默认值查到别人的数据。
- worker 两个 try：第一个只包 fn()，成功失败各算出 status 和回调参数；第二个只包回调，失败只记日志。一开始照 zhice-ai 的写法把两件事放一个 try 里，坏回调地址测试时日志记成 quiz.failed，但 Agent 其实成功了，runs 表是 done、钱也花了，而且还会再回调一个 failed 给 Go。这是 zhice-ai 四个 worker 都有的 bug，拆成两个 try 后日志变成 quiz.done 加 quiz.callback_failed。
- 三个失败场景：空文章在 with 外面抛 ValueError，202 照回、日志 quiz.failed、假 Go 收到 failed、runs 表不留记录；错 token 直接 401，require_internal 在 add_task 之前，后台什么都没跑；坏回调地址 Agent 正常跑完、run 是 done，但 Go 永远"进行中"，Python 修不了，要 Go 侧超时回收。
- 日志改成每行一个 JSON，`extra` 里的字段进 JSON，`log.exception` 自动带栈。一次任务三处能查同一个 trace_id：curl 响应、日志的 accepted / done / fake_go.complete 三行、runs 表。读长栈从下往上找第一个自己文件的帧，`'CompleteIn' object is not subscriptable` 是 pydantic 对象要用点不用方括号。

### 第 8 章 流式：SSE 与事件协议

- 解决什么问题：问答是读者在等，要边生成边显示。chat_stream 把第 1 章的流式封装成生成器逐片 yield，请求里加 `stream_options.include_usage` 最后一片才给 usage；answer_stream 把片变成事件；路由用 StreamingResponse 一片片发。
- 四种事件：meta 开头一次带 run_id 和 mode，delta 文字片段多次，done 结束带 token，error 出错时代替 done。前端只认这一套，拒答也走同一套。SSE 就是三行文本：event 行、data 行、空行。
- 读者断开后的两步收尾：路由的 events() 在 finally 里 gen.close()，生成器停着的那个 yield 处收到 GeneratorExit；answer_stream 接住后把 run.status 改成 aborted、记一条 partial 的 step，再 return。GeneratorExit 不是 Exception 的子类，tracked_run 的 except 接不到，所以要单独接；用 return 而不是 raise，让 with 正常退出走 else 分支把 aborted 写进表。验证：kill curl 后 run 68 是 aborted，content 存了半截 472 字，token 记 0 因为 usage 在最后一片没收到。
- 一个副产品：sse 返回占位符 `...` 时 events() 自己抛异常，这种情况 Starlette 没把异步生成器关干净，finally 没跑，run 60 到 62 永远 running。和读者断开不是一种情况，留给第 9 章卡住回收当测试数据。
- 攒头判标签：模型第一行的 [简短] / [详细] 会被拆成几片吐出来，不能看第一片，攒到见换行或 12 字再 split_mode，之后才发 meta。表里 content 存带标签原文，delta 发出去的不带。events() 是全教程唯一的 async，因为 StreamingResponse 要在事件循环里发，iterate_in_threadpool 把同步生成器放线程池一片片取。

### 第 9 章 稳：超时、熔断、卡住回收

- 三类问题三个对策：请求挂死靠超时，后台 60 秒、问答 20 秒，流式的超时是每次读的间隔不是整个流；厂商整体故障靠熔断器，连续失败到阈值就直接拒绝不发请求；进程被杀靠卡住回收，lifespan 里起一个协程每 5 分钟把超过 30 分钟的 running 标成 failed。
- 三态怎么转：closed 连续失败 fail_max 次变 open，open 过了 cooldown 变 half_open，half_open 只放一个试探，成功回 closed，失败再 open 一轮。状态不存变量，从 `_opened_at` 和时钟算出来，省掉"冷却到期谁来改状态"这件事。failure 里"已经打开过"和"到阈值"两个条件缺一不可，删掉前者第三个测试会红。
- 流式的判定：拿到第一片才算成功，第一片之前出错算失败，读者中途断开不算依赖失败。`except GeneratorExit: raise` 写在 `except Exception` 前面是为了说明这是有意的。
- 第一次写 pytest：Breaker 的 clock 可注入，测试里换成一个 `__call__` 返回 `self.t` 的假时钟，`clock.t = 31` 就是过了 31 秒，不用真等。`called = []` 配 lambda 验证熔断中 fn 根本没被调。骨架里两处 `...` 没填时四个用例全红，`if ...:` 因为 Ellipsis 是真值变成失败一次就打开，测试把它逮出来了。
- 验收：reap_stale 第一次跑收了 7 条，不止留着的 60 到 62，还有第 4 章进程被杀的 id 1 和第 4、5 章实验留下的 9、10、59。LLM_BASE_URL 改坏后 run 70 到 72 是 ConnectError，73 起是 CircuitOpen 且 latency 0，31 秒后的 78 是试探、再次 ConnectError 重新打开。本地 ConnectError 本身就是瞬间失败，熔断的价值在真超时场景：20 秒对 0 秒。
- 一个坑：main.py 末尾又写了一次 `app = FastAPI(..., lifespan=lifespan)`，把前面注册了路由的 app 覆盖掉，连 /health 都 404。`app = FastAPI` 全文件只能一处，且在所有 `@app` 之前；import 全部放文件头。
