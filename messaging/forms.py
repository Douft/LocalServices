from __future__ import annotations

from django import forms

from .models import SupportThread


class NewThreadForm(forms.Form):
	subject = forms.CharField(max_length=120)
	message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}))


class ReplyForm(forms.Form):
	message = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))


class ThreadStatusForm(forms.ModelForm):
	class Meta:
		model = SupportThread
		fields = ["status"]
