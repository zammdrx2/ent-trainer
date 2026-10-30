"""
Бизнес-логика тренажёра отдельно от представлений (views):
создание теста, проверка ответов и статистика по темам.
"""
import random

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .models import Answer, Choice, Question, TestAttempt, Topic


def create_attempt(user, topic: Topic | None, language: str) -> TestAttempt:
    """Создаёт тест: случайные вопросы по теме или по всем темам."""
    qs = Question.objects.filter(is_active=True)
    if topic is not None:
        qs = qs.filter(topic=topic)
        limit = settings.QUESTIONS_PER_TOPIC_TEST
    else:
        limit = settings.QUESTIONS_PER_MIXED_TEST

    ids = list(qs.values_list("id", flat=True))
    chosen = random.sample(ids, min(limit, len(ids)))

    attempt = TestAttempt.objects.create(user=user, topic=topic, language=language, total=len(chosen))
    attempt.questions.set(chosen)
    return attempt


@transaction.atomic
def grade_attempt(attempt: TestAttempt, submitted: dict[int, int | None]) -> TestAttempt:
    """
    Проверяет ответы. submitted: {id вопроса: id выбранного варианта или None}.
    Вариант засчитывается, только если он принадлежит этому вопросу.
    """
    if attempt.is_finished:
        return attempt

    questions = list(attempt.questions.all())
    valid_choices = {
        c.id: c for c in Choice.objects.filter(question__in=questions)
    }

    score = 0
    for q in questions:
        choice = valid_choices.get(submitted.get(q.id))
        if choice is not None and choice.question_id != q.id:
            choice = None  # защита от подмены варианта из другого вопроса
        is_correct = bool(choice and choice.is_correct)
        score += is_correct
        Answer.objects.update_or_create(
            attempt=attempt, question=q,
            defaults={"choice": choice, "is_correct": is_correct},
        )

    attempt.score = score
    attempt.total = len(questions)
    attempt.finished_at = timezone.now()
    attempt.save(update_fields=["score", "total", "finished_at"])
    return attempt


def topic_stats(user, language: str) -> list[dict]:
    """Процент правильных ответов ученика по каждой теме (по всем завершённым тестам)."""
    rows = (
        Answer.objects.filter(attempt__user=user, attempt__finished_at__isnull=False)
        .values("question__topic")
        .annotate(total=Count("id"), correct=Count("id", filter=Q(is_correct=True)))
    )
    by_topic = {r["question__topic"]: r for r in rows}

    stats = []
    for topic in Topic.objects.all():
        r = by_topic.get(topic.id)
        total = r["total"] if r else 0
        correct = r["correct"] if r else 0
        stats.append({
            "topic": topic,
            "name": topic.name(language),
            "total": total,
            "correct": correct,
            "percent": round(100 * correct / total) if total else None,
        })
    return stats
