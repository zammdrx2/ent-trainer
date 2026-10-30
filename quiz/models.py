"""
Модели тренажёра: темы, вопросы, варианты ответа, попытки и ответы учеников.

Каждый текст хранится на двух языках (ru / kk). Метод tr() возвращает
текст на нужном языке; если перевода нет — показывается русский вариант.
"""
from django.conf import settings
from django.db import models

LANGUAGES = (("ru", "Русский"), ("kk", "Қазақша"))


def tr(obj, field: str, lang: str) -> str:
    """Текст поля на выбранном языке с запасным вариантом на русском."""
    value = getattr(obj, f"{field}_{lang}", "") or ""
    return value or getattr(obj, f"{field}_ru", "")


class Topic(models.Model):
    name_ru = models.CharField("Название (рус)", max_length=200)
    name_kk = models.CharField("Атауы (қаз)", max_length=200, blank=True)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Тема"
        verbose_name_plural = "Темы"

    def __str__(self):
        return self.name_ru

    def name(self, lang: str) -> str:
        return tr(self, "name", lang)


class Question(models.Model):
    class Difficulty(models.IntegerChoices):
        EASY = 1, "Лёгкий"
        MEDIUM = 2, "Средний"
        HARD = 3, "Сложный"

    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="questions", verbose_name="Тема")
    text_ru = models.TextField("Вопрос (рус)")
    text_kk = models.TextField("Сұрақ (қаз)", blank=True)
    code = models.TextField("Фрагмент кода", blank=True, help_text="Необязательно: код на Python и т.п.")
    explanation_ru = models.TextField("Объяснение (рус)", blank=True)
    explanation_kk = models.TextField("Түсіндірме (қаз)", blank=True)
    difficulty = models.PositiveSmallIntegerField("Сложность", choices=Difficulty.choices, default=Difficulty.EASY)
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["topic", "id"]
        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"

    def __str__(self):
        return self.text_ru[:80]

    def text(self, lang: str) -> str:
        return tr(self, "text", lang)

    def explanation(self, lang: str) -> str:
        return tr(self, "explanation", lang)

    def correct_choice(self):
        return self.choices.filter(is_correct=True).first()


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text_ru = models.CharField("Вариант (рус)", max_length=300)
    text_kk = models.CharField("Нұсқа (қаз)", max_length=300, blank=True)
    is_correct = models.BooleanField("Правильный", default=False)

    class Meta:
        ordering = ["id"]
        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответа"

    def __str__(self):
        return self.text_ru

    def text(self, lang: str) -> str:
        return tr(self, "text", lang)


class TestAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts")
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True,
                              help_text="Пусто — смешанный тест по всем темам")
    language = models.CharField(max_length=2, choices=LANGUAGES, default="ru")
    questions = models.ManyToManyField(Question, related_name="+")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Попытка"
        verbose_name_plural = "Попытки"

    def __str__(self):
        return f"{self.user} — {self.topic or 'смешанный'} — {self.score}/{self.total}"

    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None

    @property
    def percent(self) -> int:
        return round(100 * self.score / self.total) if self.total else 0


class Answer(models.Model):
    attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    choice = models.ForeignKey(Choice, on_delete=models.SET_NULL, null=True, blank=True)
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = ("attempt", "question")
        verbose_name = "Ответ"
        verbose_name_plural = "Ответы"
