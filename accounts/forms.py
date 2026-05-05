from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Profile


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "Enter username",
            "autocomplete": "username",
        })
    )

    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-input",
            "placeholder": "Enter password",
            "autocomplete": "current-password",
        })
    )


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        label="Email",
        required=True,
        widget=forms.EmailInput(attrs={
            "class": "form-input",
            "placeholder": "Enter your email",
            "autocomplete": "email",
        })
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["username"].widget.attrs.update({
            "class": "form-input",
            "placeholder": "Choose a username",
            "autocomplete": "username",
        })

        self.fields["password1"].widget.attrs.update({
            "class": "form-input",
            "placeholder": "Create a password",
            "autocomplete": "new-password",
        })

        self.fields["password2"].widget.attrs.update({
            "class": "form-input",
            "placeholder": "Confirm your password",
            "autocomplete": "new-password",
        })

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]

        if commit:
            user.save()

        return user


class ProfileForm(forms.ModelForm):
    full_name = forms.CharField(
        label="Full Name",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "Enter your full name",
        })
    )

    email = forms.EmailField(
        label="Email",
        required=False,
        widget=forms.EmailInput(attrs={
            "class": "form-input",
            "placeholder": "Enter your email",
        })
    )

    class Meta:
        model = Profile
        fields = ["skill_level", "fitness_level", "position_preference", "experience"]
        widgets = {
            "skill_level": forms.HiddenInput(attrs={
                "class": "football-rating-input",
            }),
            "fitness_level": forms.HiddenInput(attrs={
                "class": "football-rating-input",
            }),
            "position_preference": forms.Select(attrs={
                "class": "form-input",
            }),
            "experience": forms.Select(attrs={
                "class": "form-input",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        user = self.instance.user if self.instance and self.instance.pk else None

        if user:
            full_name = user.get_full_name().strip()
            self.fields["full_name"].initial = full_name or user.username
            self.fields["email"].initial = user.email

    def save(self, commit=True):
        profile = super().save(commit=False)

        user = profile.user
        full_name = self.cleaned_data.get("full_name", "").strip()
        email = self.cleaned_data.get("email", "").strip()

        if full_name:
            name_parts = full_name.split(" ", 1)
            user.first_name = name_parts[0]
            user.last_name = name_parts[1] if len(name_parts) > 1 else ""

        user.email = email

        if commit:
            user.save()
            profile.save()

        return profile