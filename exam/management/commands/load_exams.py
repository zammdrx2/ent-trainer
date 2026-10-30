"""
Загрузка вариантов ЕНТ:  python manage.py load_exams [--reload]

Каждый вариант — папка в exam/data/ с файлом meta.json и файлами предметов
(history.json, math_lit.json, reading.json, math.json, informatics.json).

Формат файла предмета:
{
  "contexts": {"c1": {"ru": "текст", "kk": "мәтін"}},
  "tasks": [
    {"ru": "...", "kk": "...", "o": ["4", ["вар", "нұсқа"], ...], "a": 0},          # один ответ
    {"ctx": "c1", "ru": "...", "kk": "...", "o": [...], "a": 2},                   # контекстное
    {"t": "multi", "ru": "...", "kk": "...", "o": [6 вариантов], "a": [0, 3]},     # несколько ответов
    {"t": "match", "ru": "...", "kk": "...", "l": [["A", "A"], ["B", "B"]],
     "o": [4 варианта], "a": [2, 0]}                                               # соответствие
  ]
}
Вариант ответа — строка (одинаковая на обоих языках) или пара [рус, қаз].
Необязательные поля: "code" — фрагмент кода, "e": [объяснение рус, қаз].
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from exam.models import SUBJECT_INFO, ExamContext, ExamOption, ExamTask, ExamVariant

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
# Локальные материалы (например, сборники НЦТ), которые не публикуются в git.
# Файл private_data/exams/<папка варианта>/<предмет>.json заменяет одноимённый файл варианта.
PRIVATE_DIR = Path(__file__).resolve().parents[3] / "private_data" / "exams"


def pair(value):
    if isinstance(value, str):
        return value, value
    ru, kk = value
    return ru, kk or ru


class Command(BaseCommand):
    help = "Загружает варианты ЕНТ из exam/data/"

    def add_arguments(self, parser):
        parser.add_argument("--reload", action="store_true",
                            help="Перезаписать уже загруженные варианты (удалит попытки по ним)")
        parser.add_argument("--dir", default=str(DATA_DIR))

    def handle(self, *args, reload, dir, **options):
        root = Path(dir)
        folders = sorted(p for p in root.iterdir() if (p / "meta.json").exists())
        if not folders:
            raise CommandError(f"В {root} нет вариантов (папок с meta.json)")
        for folder in folders:
            self.load_variant(folder, reload)

    @transaction.atomic
    def load_variant(self, folder: Path, reload: bool):
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        variant, created = ExamVariant.objects.get_or_create(
            code=meta["code"], defaults={"title_ru": meta["title_ru"], "title_kk": meta.get("title_kk", "")}
        )
        if variant.tasks.exists():
            if not reload:
                self.stdout.write(f"{variant.code}: уже загружен, пропускаю (используйте --reload)")
                return
            variant.tasks.all().delete()
            variant.contexts.all().delete()
            variant.attempts.all().delete()
        variant.title_ru = meta["title_ru"]
        variant.title_kk = meta.get("title_kk", "")
        variant.save()

        total = 0
        for subject, info in SUBJECT_INFO.items():
            private = PRIVATE_DIR / folder.name / f"{subject}.json"
            path = private if private.exists() else folder / f"{subject}.json"
            if private.exists():
                self.stdout.write(f"{folder.name}: {subject} — из private_data")
            if not path.exists():
                raise CommandError(f"{folder.name}: нет файла {path.name}")
            data = json.loads(path.read_text(encoding="utf-8"))
            contexts = {}
            for key, c in data.get("contexts", {}).items():
                contexts[key] = ExamContext.objects.create(
                    variant=variant, key=f"{subject}-{key}", text_ru=c["ru"], text_kk=c.get("kk", ""))

            tasks = data["tasks"]
            if len(tasks) != info["tasks"]:
                raise CommandError(f"{folder.name}/{path.name}: заданий {len(tasks)}, нужно {info['tasks']}")
            for number, t in enumerate(tasks, start=1):
                self.create_task(variant, subject, number, t, contexts, f"{folder.name}/{path.name} №{number}")
            total += len(tasks)

        self.stdout.write(self.style.SUCCESS(f"{variant.code}: загружено заданий {total}"))

    def create_task(self, variant, subject, number, t, contexts, where):
        kind = t.get("t") or ("context" if "ctx" in t else "single")
        options = [pair(o) for o in t["o"]]
        answer = t["a"]
        explanation = t.get("e", ["", ""])

        task = ExamTask.objects.create(
            variant=variant, subject=subject, number=number, kind=kind,
            context=contexts.get(t["ctx"]) if "ctx" in t else None,
            text_ru=t["ru"], text_kk=t.get("kk", ""), code=t.get("code", ""),
            match_left=[list(pair(x)) for x in t.get("l", [])],
            explanation_ru=explanation[0], explanation_kk=explanation[1] if len(explanation) > 1 else "",
        )
        if "ctx" in t and t["ctx"] not in contexts:
            raise CommandError(f"{where}: нет контекста {t['ctx']}")

        if kind in ("single", "context"):
            # в ЕНТ 2026 — 4 варианта, в сборниках прошлых лет — 5 (A–E)
            if len(options) not in (4, 5) or not isinstance(answer, int) or not 0 <= answer < len(options):
                raise CommandError(f"{where}: нужно 4–5 вариантов и индекс ответа")
            flags = [(i == answer, None) for i in range(len(options))]
        elif kind == "multi":
            if len(options) != 6 or not (1 <= len(answer) <= 3) or not all(0 <= a < 6 for a in answer):
                raise CommandError(f"{where}: нужно 6 вариантов и 1–3 правильных")
            flags = [(i in answer, None) for i in range(6)]
        elif kind == "match":
            if len(t.get("l", [])) != 2 or len(answer) != 2 or answer[0] == answer[1]:
                raise CommandError(f"{where}: нужно 2 пункта слева и 2 разных ответа")
            flags = [(i in answer, (answer.index(i) + 1) if i in answer else None) for i in range(len(options))]
        else:
            raise CommandError(f"{where}: неизвестный тип {kind}")

        ExamOption.objects.bulk_create(
            ExamOption(task=task, text_ru=ru, text_kk=kk, is_correct=ok, match_slot=slot)
            for (ru, kk), (ok, slot) in zip(options, flags)
        )
