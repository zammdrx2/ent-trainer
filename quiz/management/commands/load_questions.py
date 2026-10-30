"""
Загрузка вопросов из JSON:  python manage.py load_questions [путь]
По умолчанию берётся quiz/data/questions.json. Повторный запуск не создаёт дублей.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quiz.models import Choice, Question, Topic

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "questions.json"


class Command(BaseCommand):
    help = "Загружает темы и вопросы ЕНТ из JSON-файла"

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(DEFAULT_PATH))

    @transaction.atomic
    def handle(self, *args, path, **options):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Не удалось прочитать {path}: {exc}")

        created = skipped = 0
        for order, t in enumerate(data, start=1):
            topic, _ = Topic.objects.get_or_create(
                name_ru=t["name_ru"], defaults={"name_kk": t.get("name_kk", ""), "order": order}
            )
            for q in t["questions"]:
                if Question.objects.filter(topic=topic, text_ru=q["ru"], code=q.get("code", "")).exists():
                    skipped += 1
                    continue
                answer = q["answer"]
                if not 0 <= answer < len(q["choices"]):
                    raise CommandError(f"Неверный индекс ответа в вопросе: {q['ru']}")
                question = Question.objects.create(
                    topic=topic, text_ru=q["ru"], text_kk=q.get("kk", ""), code=q.get("code", ""),
                    explanation_ru=q.get("exp_ru", ""), explanation_kk=q.get("exp_kk", ""),
                    difficulty=q.get("d", 1),
                )
                pairs = [(c, c) if isinstance(c, str) else (c[0], c[1] or c[0]) for c in q["choices"]]
                Choice.objects.bulk_create(
                    Choice(question=question, text_ru=ru, text_kk=kk, is_correct=(i == answer))
                    for i, (ru, kk) in enumerate(pairs)
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Добавлено вопросов: {created}, уже были: {skipped}"))
