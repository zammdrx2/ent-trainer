from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .ui import texts_for


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username")

    def __init__(self, *args, lang="ru", **kwargs):
        super().__init__(*args, **kwargs)
        t = texts_for(lang)
        labels = {"first_name": t["first_name"], "last_name": t["last_name"], "username": t["username"],
                  "password1": t["password"], "password2": t["password2"]}
        for name, label in labels.items():
            self.fields[name].label = label
            self.fields[name].help_text = ""


class LocalizedLoginForm(AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        lang = request.session.get("lang", "ru") if request else "ru"
        t = texts_for(lang)
        self.fields["username"].label = t["username"]
        self.fields["password"].label = t["password"]
