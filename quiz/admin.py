from django.contrib import admin

from .models import Answer, Choice, Question, TestAttempt, Topic


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4
    max_num = 6


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name_ru", "name_kk", "order", "question_count")
    list_editable = ("order",)

    @admin.display(description="Вопросов")
    def question_count(self, obj):
        return obj.questions.count()


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("short_text", "topic", "difficulty", "is_active")
    list_filter = ("topic", "difficulty", "is_active")
    search_fields = ("text_ru", "text_kk")
    inlines = [ChoiceInline]
    fieldsets = (
        (None, {"fields": ("topic", "difficulty", "is_active")}),
        ("Текст вопроса", {"fields": ("text_ru", "text_kk", "code")}),
        ("Объяснение", {"fields": ("explanation_ru", "explanation_kk")}),
    )

    @admin.display(description="Вопрос")
    def short_text(self, obj):
        return obj.text_ru[:70]


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ("question", "choice", "is_correct")
    can_delete = False


@admin.register(TestAttempt)
class TestAttemptAdmin(admin.ModelAdmin):
    """Преподаватель видит результаты всех учеников."""
    list_display = ("user", "topic", "language", "score", "total", "percent", "started_at", "finished_at")
    list_filter = ("topic", "language", "user")
    date_hierarchy = "started_at"
    inlines = [AnswerInline]
    exclude = ("questions",)
    readonly_fields = ("user", "topic", "language", "score", "total", "started_at", "finished_at")

    @admin.display(description="%")
    def percent(self, obj):
        return f"{obj.percent}%"


admin.site.site_header = "Тренажёр ЕНТ — панель преподавателя"
admin.site.site_title = "Тренажёр ЕНТ"
admin.site.index_title = "Управление вопросами и результатами"
