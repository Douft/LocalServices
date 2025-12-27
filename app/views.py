from __future__ import annotations

from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def privacy(request):
	return render(request, "privacy.html")
