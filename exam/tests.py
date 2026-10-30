import json
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import SUBJECT_INFO, ExamAttempt, ExamOption, ExamTask, ExamVariant
from .services import score_multi

DATA = Path(__file__).resolve().parent / "data"


class ScoringRulesTests(TestCase):
    """Правила НЦТ для заданий с несколькими ответами."""

    def test_one_correct(self):
        C = {1}
        self.assertEqual(score_multi(C, {1}), 2)
        self.assertEqual(score_multi(C, {1, 2}), 1)
        self.assertEqual(score_multi(C, {1, 2, 3}), 0)
        self.assertEqual(score_multi(C, {2}), 0)

    def test_two_correct(self):
        C = {1, 2}
        self.assertEqual(score_multi(C, {1, 2}), 2)
        self.assertEqual(score_multi(C, {1}), 1)
        self.assertEqual(score_multi(C, {1, 3}), 1)
        self.assertEqual(score_multi(C, {1, 2, 3}), 1)
        self.assertEqual(score_multi(C, {1, 3, 4}), 0)
        self.assertEqual(score_multi(C, set()), 0)

    def test_three_correct(self):
        C = {1, 2, 3}
        self.assertEqual(score_multi(C, {1, 2, 3}), 2)
        self.assertEqual(score_multi(C, {1, 2}), 1)
        self.assertEqual(score_multi(C, {1, 2, 4}), 1)
        self.assertEqual(score_multi(C, {1, 2, 3, 4}), 1)
        self.assertEqual(score_multi(C, {1}), 0)
        self.assertEqual(score_multi(C, {1, 4, 5}), 0)


class DataFilesTests(TestCase):
    def test_public_variants_have_ent_structure(self):
        call_command("load_exams", dir=str(DATA), verbosity=0)
        self.assertGreaterEqual(ExamVariant.objects.count(), 2)
        for v in ExamVariant.objects.all():
            self.assertEqual(v.tasks.count(), 120)
            self.assertEqual(sum(t.max_points for t in v.tasks.all()), 140)
            for subject, info in SUBJECT_INFO.items():
                self.assertEqual(v.tasks.filter(subject=subject).count(), info["tasks"])
            for subject in ("math", "informatics"):
                kinds = list(v.tasks.filter(subject=subject).values_list("kind", flat=True))
                for kind, n in (("single", 25), ("context", 5), ("multi", 5), ("match", 5)):
                    self.assertEqual(kinds.count(kind), n, f"{v.code} {subject} {kind}")
            for t in v.tasks.prefetch_related("options"):
                correct = [o for o in t.options.all() if o.is_correct]
                if t.kind in ("single", "context"):
                    self.assertEqual(len(correct), 1, str(t))
                if t.kind == "match":
                    self.assertEqual(sorted(o.match_slot for o in correct), [1, 2], str(t))
                self.assertTrue(t.text_kk, str(t))


class ExamFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_exams", dir=str(DATA), verbosity=0)
        cls.variant = ExamVariant.objects.get(code="variant-1")

    def setUp(self):
        self.user = User.objects.create_user("student", password="pass12345")
        self.client.login(username="student", password="pass12345")

    def perfect_answers(self):
        answers = {}
        for t in self.variant.tasks.prefetch_related("options"):
            opts = list(t.options.all())
            if t.kind == "match":
                answers[str(t.id)] = {str(o.match_slot): o.id for o in opts if o.match_slot}
            else:
                answers[str(t.id)] = [o.id for o in opts if o.is_correct]
        return answers

    def test_perfect_score_is_140(self):
        r = self.client.post(reverse("exam_start", args=[self.variant.id]))
        attempt = ExamAttempt.objects.get()
        self.assertRedirects(r, reverse("exam_take", args=[attempt.id]))
        self.client.post(reverse("exam_save", args=[attempt.id]),
                         data=json.dumps({"answers": self.perfect_answers()}), content_type="application/json")
        self.client.post(reverse("exam_finish", args=[attempt.id]), {"answers": "{}"})
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 140)
        self.assertEqual(attempt.section_scores["math"], 50)
        self.assertContains(self.client.get(reverse("exam_result", args=[attempt.id])), "140")

    def test_foreign_option_is_ignored(self):
        attempt = services.create_attempt(self.user, self.variant, "ru")
        t1, t2 = self.variant.tasks.filter(kind="single")[:2]
        foreign = t2.options.get(is_correct=True)
        services.save_answers(attempt, {str(t1.id): [foreign.id]})
        self.assertEqual(attempt.responses.get(task=t1).answer, [])

    def test_answers_rejected_after_deadline(self):
        attempt = services.create_attempt(self.user, self.variant, "ru")
        attempt.deadline = timezone.now() - timedelta(minutes=5)
        attempt.save()
        r = self.client.post(reverse("exam_save", args=[attempt.id]),
                             data=json.dumps({"answers": self.perfect_answers()}), content_type="application/json")
        self.assertTrue(r.json()["expired"])
        self.assertEqual(attempt.responses.count(), 0)
        # открытие просроченного теста сразу показывает результат
        r = self.client.get(reverse("exam_take", args=[attempt.id]))
        self.assertRedirects(r, reverse("exam_result", args=[attempt.id]))

    def test_partial_match_gives_one_point(self):
        attempt = services.create_attempt(self.user, self.variant, "ru")
        task = self.variant.tasks.filter(kind="match").first()
        right = {o.match_slot: o.id for o in task.options.all() if o.match_slot}
        wrong = task.options.filter(match_slot__isnull=True).first()
        services.save_answers(attempt, {str(task.id): {"1": right[1], "2": wrong.id}})
        services.finish_attempt(attempt)
        self.assertEqual(attempt.responses.get(task=task).points, 1)

    def test_other_user_cannot_open_attempt(self):
        other = User.objects.create_user("other", password="pass12345")
        attempt = services.create_attempt(other, self.variant, "ru")
        self.assertEqual(self.client.get(reverse("exam_take", args=[attempt.id])).status_code, 404)

    def test_start_resumes_unfinished_attempt(self):
        self.client.post(reverse("exam_start", args=[self.variant.id]))
        self.client.post(reverse("exam_start", args=[self.variant.id]))
        self.assertEqual(ExamAttempt.objects.count(), 1)
