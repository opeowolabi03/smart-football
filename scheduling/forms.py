from django import forms


class RatingForm(forms.Form):
    ratee_id = forms.IntegerField(widget=forms.HiddenInput())
    score = forms.IntegerField(min_value=1, max_value=5)
    comment = forms.CharField(required=False, max_length=255)
