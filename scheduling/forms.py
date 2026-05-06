from django import forms


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