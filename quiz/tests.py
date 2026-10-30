from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import Choice, Question, TestAttempt, Topic


def make_question(topic, text="2 + 2?", correct="4", wrong=("3", "5")):
    q = Question.objects.create(topic=topic, text_ru=text, text_kk=f"{text} (kk)")
    right = Choice.objects.create(question=q, text_ru=correct, is_correct=True)
    for w in wrong:
        Choice.objects.create(question=q, text_ru=w)
    return q, right


class GradingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("student", password="pass12345")
        self.topic = Topic.objects.create(name_ru="Математика", name_kk="Математика")
        self.q1, self.r1 = make_question(self.topic, "2 + 2?")
        self.q2, self.r2 = make_question(self.topic, "3 + 3?", correct="6", wrong=("5", "7"))

    def test_correct_answers_are_counted(self):
        attempt = services.create_attempt(self.user, self.topic, "ru")
        wrong = self.q2.choices.filter(is_correct=False).first()
        services.grade_attempt(attempt, {self.q1.id: self.r1.id, self.q2.id: wrong.id})
        attempt.refresh_from_db()
        self.assertEqual((attempt.score, attempt.total), (1, 2))
        self.assertEqual(attempt.percent, 50)
        self.assertTrue(attempt.is_finished)

    def test_choice_from_other_question_is_not_accepted(self):
        attempt = services.create_attempt(self.user, self.topic, "ru")
        # подставляем правильный вариант второго вопроса в ответ на первый
        services.grade_attempt(attempt, {self.q1.id: self.r2.id, self.q2.id: None})
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 0)

    def test_finished_attempt_is_not_regraded(self):
        attempt = services.create_attempt(self.user, self.topic, "ru")
        services.grade_attempt(attempt, {})
        services.grade_attempt(attempt, {self.q1.id: self.r1.id, self.q2.id: self.r2.id})
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 0)

    def test_topic_stats(self):
        attempt = services.create_attempt(self.user, self.topic, "ru")
        services.grade_attempt(attempt, {self.q1.id: self.r1.id})
        row = services.topic_stats(self.user, "ru")[0]
        self.assertEqual((row["correct"], row["total"], row["percent"]), (1, 2, 50))

    def test_translation_falls_back_to_russian(self):
        q = Question.objects.create(topic=self.topic, text_ru="Только по-русски")
        self.assertEqual(q.text("kk"), "Только по-русски")


class ViewTests(TestCase):
    def setUp(self):
        self.topic = Topic.objects.create(name_ru="Тема", name_kk="Тақырып")
        self.q, self.right = make_question(self.topic)
        self.user = User.objects.create_user("student", password="pass12345")

    def test_home_is_public(self):
        self.assertContains(self.client.get(reverse("home")), "Тема")

    def test_language_switch(self):
        self.client.post(reverse("set_language"), {"lang": "kk", "next": "/"})
        self.assertContains(self.client.get(reverse("home")), "Тақырып")

    def test_test_requires_login(self):
        r = self.client.post(reverse("start_topic", args=[self.topic.id]))
        self.assertRedirects(r, f"{reverse('login')}?next=/test/start/{self.topic.id}/")

    def test_full_flow(self):
        self.client.login(username="student", password="pass12345")
        r = self.client.post(reverse("start_topic", args=[self.topic.id]))
        attempt = TestAttempt.objects.get()
        self.assertRedirects(r, reverse("take_test", args=[attempt.id]))

        r = self.client.post(reverse("take_test", args=[attempt.id]), {f"q{self.q.id}": self.right.id})
        self.assertRedirects(r, reverse("result", args=[attempt.id]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 1)
        self.assertEqual(self.client.get(reverse("stats")).status_code, 200)

    def test_cannot_open_other_users_attempt(self):
        other = User.objects.create_user("other", password="pass12345")
        attempt = services.create_attempt(other, self.topic, "ru")
        self.client.login(username="student", password="pass12345")
        self.assertEqual(self.client.get(reverse("take_test", args=[attempt.id])).status_code, 404)

    def test_signup(self):
        r = self.client.post(reverse("signup"), {
            "first_name": "Айжан", "last_name": "Серік", "username": "aizhan",
            "password1": "strongpass123", "password2": "strongpass123",
        })
        self.assertRedirects(r, reverse("home"))
        self.assertTrue(User.objects.filter(username="aizhan").exists())


class LoadQuestionsTests(TestCase):
    def test_load_is_idempotent_and_has_one_correct_answer(self):
        call_command("load_questions", verbosity=0)
        count = Question.objects.count()
        self.assertGreaterEqual(count, 40)
        call_command("load_questions", verbosity=0)
        self.assertEqual(Question.objects.count(), count)
        for q in Question.objects.all():
            self.assertEqual(q.choices.filter(is_correct=True).count(), 1, q.text_ru)
            self.assertTrue(q.text_kk, q.text_ru)
