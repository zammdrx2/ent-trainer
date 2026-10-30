"""
Логика режима ЕНТ: создание попытки, сохранение ответов, подсчёт баллов по правилам НЦТ.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import SUBJECT_INFO, SUBJECT_ORDER, ExamAttempt, ExamResponse, ExamTask, ExamVariant

# Небольшой запас времени на сетевую задержку при последнем сохранении
GRACE = timedelta(seconds=30)


# ---------- Подсчёт баллов ----------

def score_multi(correct: set, selected: set) -> int:
    """
    Задания с несколькими правильными ответами (правила НЦТ):
      все правильные и ни одного лишнего          → 2 балла
      1 ответ:  правильный + один неверный       → 1 балл
      2 ответа: один правильный (± один неверный),
                оба правильных + один неверный    → 1 балл
      3 ответа: два правильных (± один неверный),
                три правильных + один неверный    → 1 балл
      два и более неверных                        → 0 баллов
    """
    k = len(correct)
    c = len(selected & correct)
    w = len(selected - correct)
    if k == 0 or c == 0 or w >= 2:
        return 0
    if c == k and w == 0:
        return 2
    if k == 1:
        return 1  # один правильный и один неверный
    return 1 if c >= k - 1 else 0


def score_task(task: ExamTask, answer) -> int:
    options = list(task.options.all())
    if task.kind in (ExamTask.Kind.SINGLE, ExamTask.Kind.CONTEXT):
        if not isinstance(answer, list) or len(answer) != 1:
            return 0
        return int(any(o.id == answer[0] and o.is_correct for o in options))

    if task.kind == ExamTask.Kind.MULTI:
        if not isinstance(answer, list):
            return 0
        correct = {o.id for o in options if o.is_correct}
        return score_multi(correct, set(answer))

    if task.kind == ExamTask.Kind.MATCH:
        if not isinstance(answer, dict):
            return 0
        right = {o.match_slot: o.id for o in options if o.match_slot}
        hits = sum(1 for slot in (1, 2) if answer.get(str(slot)) == right.get(slot))
        return hits  # 2 верных → 2 балла, 1 → 1 балл
    return 0


# ---------- Попытки ----------

def create_attempt(user, variant: ExamVariant, language: str) -> ExamAttempt:
    now = timezone.now()
    return ExamAttempt.objects.create(
        user=user, variant=variant, language=language,
        deadline=now + timedelta(minutes=variant.duration_minutes),
    )


def time_left(attempt: ExamAttempt) -> int:
    """Оставшееся время в секундах (не меньше 0)."""
    return max(0, int((attempt.deadline - timezone.now()).total_seconds()))


def is_expired(attempt: ExamAttempt) -> bool:
    return timezone.now() > attempt.deadline + GRACE


def clean_answer(task: ExamTask, raw, valid_ids: set):
    """Оставляет только варианты этого задания; приводит ответ к нужному виду."""
    if task.kind in (ExamTask.Kind.SINGLE, ExamTask.Kind.CONTEXT):
        ids = [i for i in (raw if isinstance(raw, list) else [raw]) if isinstance(i, int) and i in valid_ids]
        return ids[:1]
    if task.kind == ExamTask.Kind.MULTI:
        ids = [i for i in (raw if isinstance(raw, list) else []) if isinstance(i, int) and i in valid_ids]
        return sorted(set(ids))[:6]
    if task.kind == ExamTask.Kind.MATCH:
        if not isinstance(raw, dict):
            return {}
        return {s: raw[s] for s in ("1", "2") if isinstance(raw.get(s), int) and raw[s] in valid_ids}
    return []


@transaction.atomic
def save_answers(attempt: ExamAttempt, answers: dict) -> int:
    """answers: {"<id задания>": ответ}. Возвращает число сохранённых ответов."""
    if attempt.is_finished or is_expired(attempt):
        return 0
    ids = [int(k) for k in answers if str(k).isdigit()]
    tasks = ExamTask.objects.filter(variant=attempt.variant, id__in=ids).prefetch_related("options")
    saved = 0
    for task in tasks:
        valid = {o.id for o in task.options.all()}
        answer = clean_answer(task, answers.get(str(task.id), answers.get(task.id)), valid)
        ExamResponse.objects.update_or_create(attempt=attempt, task=task, defaults={"answer": answer})
        saved += 1
    return saved


@transaction.atomic
def finish_attempt(attempt: ExamAttempt) -> ExamAttempt:
    """Подсчитывает баллы по всем заданиям и закрывает попытку."""
    if attempt.is_finished:
        return attempt
    responses = {r.task_id: r for r in attempt.responses.all()}
    sections = {s: 0 for s in SUBJECT_ORDER}
    tasks = ExamTask.objects.filter(variant=attempt.variant).prefetch_related("options")
    for task in tasks:
        resp = responses.get(task.id)
        pts = score_task(task, resp.answer) if resp else 0
        if resp and resp.points != pts:
            resp.points = pts
            resp.save(update_fields=["points"])
        sections[task.subject] = sections.get(task.subject, 0) + pts

    attempt.section_scores = sections
    attempt.score = sum(sections.values())
    attempt.finished_at = min(timezone.now(), attempt.deadline + GRACE)
    attempt.save(update_fields=["section_scores", "score", "finished_at"])
    return attempt


def section_summary(attempt: ExamAttempt, lang: str) -> list[dict]:
    from .models import subject_name
    rows = []
    for s in SUBJECT_ORDER:
        info = SUBJECT_INFO[s]
        got = attempt.section_scores.get(s, 0)
        rows.append({
            "subject": s, "name": subject_name(s, lang), "score": got, "max": info["max"],
            "threshold": info["threshold"], "passed": got >= info["threshold"],
            "percent": round(100 * got / info["max"]),
        })
    return rows
