import json
import random

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from quiz.ui import get_lang

from . import services
from .models import SUBJECT_INFO, SUBJECT_ORDER, ExamAttempt, ExamTask, ExamVariant, subject_name
from .ui import exam_texts

LETTERS = "ABCDEFGH"


@login_required
def exam_home(request):
    lang = get_lang(request)
    variants = ExamVariant.objects.filter(is_active=True)
    attempts = request.user.exam_attempts.select_related("variant")
    active = {a.variant_id: a for a in attempts if not a.is_finished and not services.is_expired(a)}
    best = {}
    for a in attempts:
        if a.is_finished and a.score >= best.get(a.variant_id, -1):
            best[a.variant_id] = a.score
    cards = [{"v": v, "title": v.title(lang), "active": active.get(v.id), "best": best.get(v.id)} for v in variants]
    structure = [
        {"name": subject_name(s, lang), "tasks": SUBJECT_INFO[s]["tasks"], "max": SUBJECT_INFO[s]["max"],
         "threshold": SUBJECT_INFO[s]["threshold"]}
        for s in SUBJECT_ORDER
    ]
    history = [{"a": a, "title": a.variant.title(lang)} for a in attempts if a.is_finished][:20]
    return render(request, "exam/home.html", {
        "cards": cards, "structure": structure, "history": history, "et": exam_texts(lang),
    })


@login_required
@require_POST
def exam_start(request, variant_id):
    variant = get_object_or_404(ExamVariant, pk=variant_id, is_active=True)
    existing = request.user.exam_attempts.filter(variant=variant, finished_at__isnull=True).first()
    if existing and not services.is_expired(existing):
        return redirect("exam_take", attempt_id=existing.id)
    if existing:
        services.finish_attempt(existing)
    attempt = services.create_attempt(request.user, variant, get_lang(request))
    return redirect("exam_take", attempt_id=attempt.id)


def _build_sections(attempt: ExamAttempt, lang: str, with_answers: bool = False):
    """Задания, сгруппированные по предметам. Варианты ответов перемешаны, но постоянно для попытки."""
    tasks = (ExamTask.objects.filter(variant=attempt.variant)
             .select_related("context").prefetch_related("options"))
    responses = {r.task_id: r for r in attempt.responses.all()}
    by_subject = {s: [] for s in SUBJECT_ORDER}
    for task in tasks:
        options = list(task.options.all())
        random.Random(attempt.id * 1_000_003 + task.id).shuffle(options)
        resp = responses.get(task.id)
        item = {
            "id": task.id, "number": task.number, "kind": task.kind, "max": task.max_points,
            "text": task.text(lang), "code": task.code,
            "context_id": task.context_id, "context": task.context.text(lang) if task.context else "",
            "options": [{"id": o.id, "letter": LETTERS[i], "text": o.text(lang),
                         "correct": o.is_correct, "slot": o.match_slot} for i, o in enumerate(options)],
            "left": [task.left_item(1, lang), task.left_item(2, lang)] if task.kind == ExamTask.Kind.MATCH else [],
            "answer": resp.answer if resp else None,
        }
        if with_answers:
            item["points"] = resp.points if resp else 0
            item["explanation"] = task.explanation(lang)
            chosen = resp.answer if resp else None
            if task.kind == ExamTask.Kind.MATCH:
                chosen = chosen or {}
                letter = {o["id"]: o["letter"] for o in item["options"]}
                item["match_rows"] = [{
                    "left": item["left"][slot - 1],
                    "chosen": letter.get(chosen.get(str(slot))),
                    "right": next((o["letter"] for o in item["options"] if o["slot"] == slot), ""),
                } for slot in (1, 2)]
            else:
                chosen_ids = set(chosen or [])
                for o in item["options"]:
                    o["chosen"] = o["id"] in chosen_ids
        by_subject[task.subject].append(item)

    sections = []
    for s in SUBJECT_ORDER:
        items = sorted(by_subject[s], key=lambda x: x["number"])
        prev_ctx = None
        for it in items:
            it["show_context"] = bool(it["context_id"]) and it["context_id"] != prev_ctx
            prev_ctx = it["context_id"]
        sections.append({"subject": s, "name": subject_name(s, lang), "items": items,
                         "max": SUBJECT_INFO[s]["max"]})
    return sections


@login_required
def exam_take(request, attempt_id):
    attempt = get_object_or_404(ExamAttempt, pk=attempt_id, user=request.user)
    if attempt.is_finished:
        return redirect("exam_result", attempt_id=attempt.id)
    if services.is_expired(attempt):
        services.finish_attempt(attempt)
        return redirect("exam_result", attempt_id=attempt.id)

    lang = attempt.language
    sections = _build_sections(attempt, lang)
    saved = {str(it["id"]): it["answer"] for s in sections for it in s["items"] if it["answer"] not in (None, [], {})}
    return render(request, "exam/take.html", {
        "attempt": attempt, "sections": sections, "title": attempt.variant.title(lang),
        "seconds_left": services.time_left(attempt), "saved_json": json.dumps(saved),
        "et": exam_texts(lang),
    })


@login_required
@require_POST
def exam_save(request, attempt_id):
    attempt = get_object_or_404(ExamAttempt, pk=attempt_id, user=request.user)
    if attempt.is_finished or services.is_expired(attempt):
        return JsonResponse({"ok": False, "expired": True})
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "bad json"}, status=400)
    saved = services.save_answers(attempt, payload.get("answers", {}))
    return JsonResponse({"ok": True, "saved": saved, "seconds_left": services.time_left(attempt)})


@login_required
@require_POST
def exam_finish(request, attempt_id):
    attempt = get_object_or_404(ExamAttempt, pk=attempt_id, user=request.user)
    if not attempt.is_finished:
        try:
            answers = json.loads(request.POST.get("answers", "{}"))
        except json.JSONDecodeError:
            answers = {}
        if isinstance(answers, dict):
            services.save_answers(attempt, answers)  # ничего не сохранит, если время вышло
        services.finish_attempt(attempt)
    return redirect("exam_result", attempt_id=attempt.id)


@login_required
def exam_result(request, attempt_id):
    attempt = get_object_or_404(ExamAttempt, pk=attempt_id, user=request.user)
    if not attempt.is_finished:
        if services.is_expired(attempt):
            services.finish_attempt(attempt)
        else:
            return redirect("exam_take", attempt_id=attempt.id)
    lang = get_lang(request)
    summary = services.section_summary(attempt, lang)
    used = attempt.finished_at - attempt.started_at
    minutes = int(used.total_seconds() // 60)
    return render(request, "exam/result.html", {
        "attempt": attempt, "summary": summary, "all_passed": all(r["passed"] for r in summary),
        "sections": _build_sections(attempt, lang, with_answers=True),
        "title": attempt.variant.title(lang), "minutes": minutes, "et": exam_texts(lang),
    })
