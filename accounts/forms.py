from django import forms
from .models import Profile

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["skill_level", "fitness_level", "position_preference", "experience"]
