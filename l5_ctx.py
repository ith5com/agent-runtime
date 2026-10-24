from llm import MODEL
from runtime import run_loop
from runs import init_db, tracked_run, get_run
from l3_agent import TOOLS, send

Q = "现在几点，今天天气怎么样，另外 17 加 25 等于多少"


def run_agent(question: str, *, max_steps: int = 6, abort: bool = False) -> int:
    with tracked_run(agent="l5", model=MODEL) as run:
        r = run_loop(send, [{"role": "user", "content": question}], TOOLS, run=run, max_steps=max_steps)
        if r.hit_max_steps:
            raise RuntimeError("撞到步数上限")
        if abort:
            run.status = "aborted"
    return run.id


if __name__ == "__main__":
    init_db()

    # 情况一：正常
    rid1 = run_agent(Q)

    # 情况二：撞上限，run_agent 会 raise，接住
    try:
        run_agent(Q, max_steps=1)
    except RuntimeError as e:
        print("情况二 raise 了：", e)

    # 情况三：块里改成 aborted
    rid3 = run_agent(Q, abort=True)

    # 三条读出来看
    for rid in (rid1, rid1 + 1, rid3):
        run = get_run(rid)
        print(f"run {rid}: status={run['status']} tokens={run['input_tokens']}+{run['output_tokens']} error={run['error']}")


# 备注：两个问题的答案
#
# 1. 情况二里 raise RuntimeError 之后，finish_run 在哪被调？status 是什么？
#    异常从 with 块冒出来，落到 tracked_run 里 yield 那一行，被它的 except 接住。
#    except 分支调 finish_run，status="failed"，error 是 repr(e) 也就是 RuntimeError('撞到步数上限')，
#    然后裸 raise 把异常继续往外抛，所以 if __name__ 里的 try 才能接到它。
#    run_agent 自己没有写任何记账代码，收尾全是 tracked_run 做的。
#
# 2. run.status = "aborted" 为什么要写在 with 块里？写在 return 前面那行行不行？
#    不行。with 块一结束，tracked_run 的 else 分支就立刻跑了，finish_run 已经把 status 写进表。
#    写在 return 前面等于 with 结束之后再改，表里已经是 done，改内存里的 run.status 没用了。
#    规律：要影响 finish_run 写什么，必须在 with 块结束之前改。
