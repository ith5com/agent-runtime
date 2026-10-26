from pydantic import BaseModel, Field
from llm import chat, MODEL
from runs import init_db, tracked_run
from structured import invoke_structured

class Question(BaseModel):
    stem: str = Field(description="题干，一句话，考察理解不考察背诵")
    options: list[str] = Field(description="四个选项的文字，不带 A B C D 前缀")
    answer: int = Field(description="正确选项的下标，0 到 3")


class Quiz(BaseModel):
    """根据给定文章出的一组选择题"""
    points: list[str] = Field(description="文章的 3 到 5 个要点，每条一句话")
    questions: list[Question] = Field(description="选择题列表")


def check_quiz(quiz: Quiz) -> list[str]:
    problems = []
    MIN_QUESTIONS = 10
    if len(quiz.questions) < MIN_QUESTIONS:
        problems.append(f"至少 {MIN_QUESTIONS} 题，现在 {len(quiz.questions)} 题")

    for i, q in enumerate(quiz.questions, 1):
        if len(q.options) != 4:
            problems.append(f"第 {i} 题有 {len(q.options)} 个选项，要 4 个")

        if not 0 <= q.answer <= 3:
            problems.append(f"第 {i} 题 answer 是 {q.answer}，合法范围是 0 到 3")
    return problems




ARTICLE = """...500 字..."""
SYSTEM = "你是出题老师。根据用户给的文章出选择题，题目要能考察理解。"


def make_quiz(article: str) -> tuple[Quiz, int]:
    """返回 (结果, 用了几次尝试)。"""
    with tracked_run(agent="l6", model=MODEL) as run:
        quiz = invoke_structured(chat, [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": article},
        ], Quiz, check=check_quiz, run=run)
        return quiz, run.seq


if __name__ == "__main__":
    init_db()
    first, retried, failed = 0, 0, 0
    for i in range(3):
        try:
            quiz, tries = make_quiz(ARTICLE)
            if tries == 1:
                first += 1
            else:
                retried += 1
            print(f"第 {i+1} 轮：{len(quiz.questions)} 题，{tries} 次尝试")
        except RuntimeError as e:
            failed += 1
            print(f"第 {i+1} 轮失败：{e}")
    print(f"一次合格 {first}，打回后合格 {retried}，失败 {failed}")