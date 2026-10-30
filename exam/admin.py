from django.contrib import admin

from .models import ExamAttempt, ExamContext, ExamOption, ExamResponse, ExamTask, ExamVariant


class OptionInline(admin.TabularInline):
    model = ExamOption
    extra = 0
    fields = ("text_ru", "text_kk", "is_correct", "match_slot")


@admin.register(ExamVariant)
class ExamVariantAdmin(admin.ModelAdmin):
    list_display = ("code", "title_ru", "duration_minutes", "is_active", "task_count")
    list_editable = ("is_active",)

    @admin.display(description="Заданий")
    def task_count(self, obj):
        return obj.tasks.count()


@admin.register(ExamContext)
class ExamContextAdmin(admin.ModelAdmin):
    list_display = ("variant", "key", "short")
    list_filter = ("variant",)

    @admin.display(description="Текст")
    def short(self, obj):
        return obj.text_ru[:80]


@admin.register(ExamTask)
class ExamTaskAdmin(admin.ModelAdmin):
    list_display = ("variant", "subject", "number", "kind", "short")
    list_filter = ("variant", "subject", "kind")
    search_fields = ("text_ru", "text_kk")
    inlines = [OptionInline]

    @admin.display(description="Задание")
    def short(self, obj):
        return obj.text_ru[:70]


class ResponseInline(admin.TabularInline):
    model = ExamResponse
    extra = 0
    readonly_fields = ("task", "answer", "points")
    can_delete = False


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "variant", "language", "score", "started_at", "finished_at")
    list_filter = ("variant", "language")
    readonly_fields = ("user", "variant", "language", "started_at", "deadline", "finished_at", "score", "section_scores")
    inlines = [ResponseInline]
