from django import forms
from django.contrib.auth import get_user_model

from .models import MatchResult


User = get_user_model()


class RatingForm(forms.Form):
    score = forms.ChoiceField(
        label="Rating",
        required=False,
        choices=[
            ("1", "1"),
            ("2", "2"),
            ("3", "3"),
            ("4", "4"),
            ("5", "5"),
        ],
        widget=forms.RadioSelect(attrs={
            "class": "feedback-score-input",
        }),
    )

    comment = forms.CharField(
        label="Comment",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-input feedback-comment-box",
            "placeholder": "Optional comment about this player's performance...",
            "rows": 3,
            "maxlength": 255,
        }),
    )


class MatchResultForm(forms.ModelForm):
    class Meta:
        model = MatchResult
        fields = [
            "team_a_score",
            "team_b_score",
            "team_a_possession",
            "team_b_possession",
            "team_a_shots",
            "team_b_shots",
            "team_a_chances",
            "team_b_chances",
            "team_a_pass_accuracy",
            "team_b_pass_accuracy",
            "team_a_tackles",
            "team_b_tackles",
            "mvp",
            "notes",
        ]

        widgets = {
            "team_a_score": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
            }),
            "team_b_score": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
            }),

            "team_a_possession": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
                "max": "100",
            }),
            "team_b_possession": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
                "max": "100",
            }),

            "team_a_shots": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
            }),
            "team_b_shots": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
            }),

            "team_a_chances": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
            }),
            "team_b_chances": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
            }),

            "team_a_pass_accuracy": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
                "max": "100",
            }),
            "team_b_pass_accuracy": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
                "max": "100",
            }),

            "team_a_tackles": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
            }),
            "team_b_tackles": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "0",
            }),

            "mvp": forms.Select(attrs={
                "class": "form-input",
            }),

            "notes": forms.Textarea(attrs={
                "class": "form-input",
                "rows": 4,
                "placeholder": "Add a short match summary, key moments, or organiser notes...",
            }),
        }

        labels = {
            "team_a_score": "Team A Score",
            "team_b_score": "Team B Score",

            "team_a_possession": "Team A Possession %",
            "team_b_possession": "Team B Possession %",

            "team_a_shots": "Team A Shots",
            "team_b_shots": "Team B Shots",

            "team_a_chances": "Team A Chances",
            "team_b_chances": "Team B Chances",

            "team_a_pass_accuracy": "Team A Pass Accuracy %",
            "team_b_pass_accuracy": "Team B Pass Accuracy %",

            "team_a_tackles": "Team A Tackles",
            "team_b_tackles": "Team B Tackles",

            "mvp": "Player of the Match",
            "notes": "Match Notes",
        }

    def __init__(self, *args, session=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["mvp"].required = False
        self.fields["mvp"].empty_label = "No MVP selected"

        if session:
            participant_user_ids = session.participants.values_list(
                "user_id",
                flat=True,
            )

            self.fields["mvp"].queryset = (
                User.objects
                .filter(id__in=participant_user_ids)
                .order_by("username")
            )
        else:
            self.fields["mvp"].queryset = User.objects.none()

    def clean(self):
        cleaned_data = super().clean()

        team_a_possession = cleaned_data.get("team_a_possession")
        team_b_possession = cleaned_data.get("team_b_possession")

        if team_a_possession is not None and team_b_possession is not None:
            if team_a_possession + team_b_possession != 100:
                raise forms.ValidationError(
                    "Team A and Team B possession must add up to 100%."
                )

        return cleaned_data