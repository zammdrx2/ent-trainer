from .ui import get_lang, texts_for


def ui(request):
    """Добавляет в каждый шаблон текущий язык и словарь текстов интерфейса (t)."""
    lang = get_lang(request)
    return {"lang": lang, "t": texts_for(lang)}
