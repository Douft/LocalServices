from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from analyticsapp.reporting import build_reports_context


@staff_member_required
def reports(request):
	ctx = build_reports_context(days=30)
	return render(
		request,
		"admin/reports.html",
		ctx,
	)
