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
