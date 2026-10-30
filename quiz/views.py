import random

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import services
from .forms import SignUpForm
from .models import Answer, Topic, TestAttempt
from .ui import SUPPORTED, get_lang, texts_for


def home(request):
    lang = get_lang(request)
    topics = Topic.objects.annotate(n=Count("questions", filter=Q(questions__is_active=True)))
    cards = [{"topic": t, "name": t.name(lang), "n": t.n} for t in topics]
    unfinished = None
    if request.user.is_authenticated:
        unfinished = request.user.attempts.filter(finished_at__isnull=True).first()
    return render(request, "quiz/home.html", {"cards": cards, "unfinished": unfinished})


@require_POST
def set_language(request):
    lang = request.POST.get("lang")
    if lang in SUPPORTED:
        request.session["lang"] = lang
    next_url = request.POST.get("next", "/")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = "/"
    return redirect(next_url)


def signup(request):
    lang = get_lang(request)
    form = SignUpForm(request.POST or None, lang=lang)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("home")
    return render(request, "registration/signup.html", {"form": form})


@login_required
@require_POST
def start_test(request, topic_id=None):
    lang = get_lang(request)
    topic = get_object_or_404(Topic, pk=topic_id) if topic_id else None
    attempt = services.create_attempt(request.user, topic, lang)
    if attempt.total == 0:
        attempt.delete()
        messages.warning(request, texts_for(lang)["no_questions"])
        return redirect("home")
    return redirect("take_test", attempt_id=attempt.id)


def _ordered_questions(attempt):
    """Вопросы теста в случайном, но постоянном для этой попытки порядке."""
    questions = list(attempt.questions.select_related("topic").prefetch_related("choices").order_by("id"))
    random.Random(attempt.id).shuffle(questions)
    return questions


def _shuffled_choices(attempt, question, lang):
    """Варианты в случайном, но постоянном для этой попытки порядке."""
    choices = list(question.choices.all())
    random.Random(attempt.id * 100_000 + question.id).shuffle(choices)
    return [{"id": c.id, "text": c.text(lang), "is_correct": c.is_correct} for c in choices]


@login_required
def take_test(request, attempt_id):
    attempt = get_object_or_404(TestAttempt, pk=attempt_id, user=request.user)
    if attempt.is_finished:
        return redirect("result", attempt_id=attempt.id)

    if request.method == "POST":
        submitted = {}
        for q in attempt.questions.all():
            raw = request.POST.get(f"q{q.id}")
            submitted[q.id] = int(raw) if raw and raw.isdigit() else None
        services.grade_attempt(attempt, submitted)
        return redirect("result", attempt_id=attempt.id)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])

    lang = attempt.language
    questions = _ordered_questions(attempt)
    items = [
        {"q": q, "text": q.text(lang), "code": q.code, "choices": _shuffled_choices(attempt, q, lang)}
        for q in questions
    ]
    title = attempt.topic.name(lang) if attempt.topic else texts_for(lang)["mixed_test"]
    return render(request, "quiz/test.html", {"attempt": attempt, "items": items, "title": title})


@login_required
def result(request, attempt_id):
    attempt = get_object_or_404(TestAttempt, pk=attempt_id, user=request.user)
    if not attempt.is_finished:
        return redirect("take_test", attempt_id=attempt.id)

    lang = get_lang(request)
    answers = {a.question_id: a for a in Answer.objects.filter(attempt=attempt)}
    items = []
    for q in _ordered_questions(attempt):
        a = answers.get(q.id)
        correct = q.correct_choice()
        items.append({
            "text": q.text(lang),
            "code": q.code,
            "is_correct": bool(a and a.is_correct),
            "chosen": a.choice.text(lang) if a and a.choice else None,
            "correct": correct.text(lang) if correct else "",
            "explanation": q.explanation(lang),
        })
    title = attempt.topic.name(lang) if attempt.topic else texts_for(lang)["mixed_test"]
    return render(request, "quiz/result.html", {"attempt": attempt, "items": items, "title": title})


@login_required
def stats(request):
    lang = get_lang(request)
    topic_rows = services.topic_stats(request.user, lang)
    weak = sorted(
        (r for r in topic_rows if r["percent"] is not None and r["percent"] < 70),
        key=lambda r: r["percent"],
    )
    finished = request.user.attempts.filter(finished_at__isnull=False).select_related("topic")
    history = [
        {"a": a, "name": a.topic.name(lang) if a.topic else texts_for(lang)["mixed_test"]}
        for a in finished[:30]
    ]
    count = finished.count()
    avg = round(sum(a.percent for a in finished) / count) if count else None
    return render(request, "quiz/stats.html", {
        "topic_rows": topic_rows, "weak": weak, "history": history, "count": count, "avg": avg,
    })
