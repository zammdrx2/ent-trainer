"""
Модели режима «Полный ЕНТ».

Структура повторяет формат ЕНТ: 5 предметов, 120 заданий, максимум 140 баллов, 240 минут.
Типы заданий:
  single  — один правильный ответ из 4 (1 балл)
  context — один ответ из 4, задание к общему тексту/ситуации (1 балл)
  multi   — от 1 до 3 правильных ответов из 6 (до 2 баллов)
  match   — соответствие: два пункта слева, у каждого свой правильный вариант (до 2 баллов)
"""
from django.conf import settings
from django.db import models

from quiz.models import LANGUAGES, tr


class Subject(models.TextChoices):
    HISTORY = "history", "История Казахстана"
    MATH_LIT = "math_lit", "Математическая грамотность"
    READING = "reading", "Грамотность чтения"
    MATH = "math", "Математика"
    INFORMATICS = "informatics", "Информатика"


SUBJECT_INFO = {
    # порядок, название (ru, kk), число заданий, максимум баллов, пороговый балл
    Subject.HISTORY: {"order": 1, "ru": "История Казахстана", "kk": "Қазақстан тарихы", "tasks": 20, "max": 20, "threshold": 5},
    Subject.MATH_LIT: {"order": 2, "ru": "Математическая грамотность", "kk": "Математикалық сауаттылық", "tasks": 10, "max": 10, "threshold": 3},
    Subject.READING: {"order": 3, "ru": "Грамотность чтения", "kk": "Оқу сауаттылығы", "tasks": 10, "max": 10, "threshold": 3},
    Subject.MATH: {"order": 4, "ru": "Математика", "kk": "Математика", "tasks": 40, "max": 50, "threshold": 5},
    Subject.INFORMATICS: {"order": 5, "ru": "Информатика", "kk": "Информатика", "tasks": 40, "max": 50, "threshold": 5},
}
SUBJECT_ORDER = sorted(SUBJECT_INFO, key=lambda s: SUBJECT_INFO[s]["order"])


def subject_name(subject: str, lang: str) -> str:
    info = SUBJECT_INFO[subject]
    return info.get(lang) or info["ru"]


class ExamVariant(models.Model):
    code = models.SlugField("Код", unique=True)
    title_ru = models.CharField("Название (рус)", max_length=200)
    title_kk = models.CharField("Атауы (қаз)", max_length=200, blank=True)
    duration_minutes = models.PositiveIntegerField("Длительность, мин", default=240)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Вариант ЕНТ"
        verbose_name_plural = "Варианты ЕНТ"

    def __str__(self):
        return self.title_ru

    def title(self, lang: str) -> str:
        return tr(self, "title", lang)


class ExamContext(models.Model):
    """Общий текст или ситуация, к которой относятся несколько заданий."""
    variant = models.ForeignKey(ExamVariant, on_delete=models.CASCADE, related_name="contexts")
    key = models.CharField(max_length=30)
    text_ru = models.TextField("Текст (рус)")
    text_kk = models.TextField("Мәтін (қаз)", blank=True)

    class Meta:
        unique_together = ("variant", "key")
        verbose_name = "Контекст (текст к заданиям)"
        verbose_name_plural = "Контексты"

    def __str__(self):
        return f"{self.variant.code}: {self.text_ru[:60]}"

    def text(self, lang: str) -> str:
        return tr(self, "text", lang)


class ExamTask(models.Model):
    class Kind(models.TextChoices):
        SINGLE = "single", "Один ответ"
        CONTEXT = "context", "Контекстное"
        MULTI = "multi", "Несколько ответов"
        MATCH = "match", "Соответствие"

    variant = models.ForeignKey(ExamVariant, on_delete=models.CASCADE, related_name="tasks")
    subject = models.CharField("Предмет", max_length=20, choices=Subject.choices)
    number = models.PositiveIntegerField("Номер в предмете")
    kind = models.CharField("Тип", max_length=10, choices=Kind.choices, default=Kind.SINGLE)
    context = models.ForeignKey(ExamContext, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
    text_ru = models.TextField("Задание (рус)")
    text_kk = models.TextField("Тапсырма (қаз)", blank=True)
    code = models.TextField("Фрагмент кода", blank=True)
    # для заданий на соответствие: два пункта левого столбца [[ru, kk], [ru, kk]]
    match_left = models.JSONField("Пункты слева (соответствие)", default=list, blank=True)
    explanation_ru = models.TextField("Объяснение (рус)", blank=True)
    explanation_kk = models.TextField("Түсіндірме (қаз)", blank=True)

    class Meta:
        ordering = ["variant", "subject", "number"]
        unique_together = ("variant", "subject", "number")
        verbose_name = "Задание ЕНТ"
        verbose_name_plural = "Задания ЕНТ"

    def __str__(self):
        return f"{self.variant.code} · {self.get_subject_display()} · №{self.number}"

    @property
    def max_points(self) -> int:
        return 2 if self.kind in (self.Kind.MULTI, self.Kind.MATCH) else 1

    def text(self, lang: str) -> str:
        return tr(self, "text", lang)

    def explanation(self, lang: str) -> str:
        return tr(self, "explanation", lang)

    def left_item(self, slot: int, lang: str) -> str:
        ru, kk = self.match_left[slot - 1]
        return (kk if lang == "kk" and kk else ru)


class ExamOption(models.Model):
    task = models.ForeignKey(ExamTask, on_delete=models.CASCADE, related_name="options")
    text_ru = models.CharField("Вариант (рус)", max_length=500)
    text_kk = models.CharField("Нұсқа (қаз)", max_length=500, blank=True)
    is_correct = models.BooleanField("Правильный", default=False)
    # для соответствия: номер пункта слева (1 или 2), к которому этот вариант подходит
    match_slot = models.PositiveSmallIntegerField("Пункт слева (соответствие)", null=True, blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответа"

    def __str__(self):
        return self.text_ru

    def text(self, lang: str) -> str:
        return tr(self, "text", lang)


class ExamAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_attempts")
    variant = models.ForeignKey(ExamVariant, on_delete=models.CASCADE, related_name="attempts")
    language = models.CharField(max_length=2, choices=LANGUAGES, default="ru")
    started_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveIntegerField(default=0)
    section_scores = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Попытка ЕНТ"
        verbose_name_plural = "Попытки ЕНТ"

    def __str__(self):
        return f"{self.user} — {self.variant.code} — {self.score}/140"

    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None


class ExamResponse(models.Model):
    """
    Ответ ученика на задание. answer:
      single/context — [id варианта]
      multi          — [id, id, ...]
      match          — {"1": id, "2": id}
    """
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="responses")
    task = models.ForeignKey(ExamTask, on_delete=models.CASCADE)
    answer = models.JSONField(default=list, blank=True)
    points = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("attempt", "task")
        verbose_name = "Ответ ЕНТ"
        verbose_name_plural = "Ответы ЕНТ"
