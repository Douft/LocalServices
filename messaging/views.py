from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import NewThreadForm, ReplyForm
from .models import SupportMessage, SupportThread


@login_required
def inbox(request):
	threads = SupportThread.objects.filter(user=request.user).order_by("-updated_at")
	return render(request, "messaging/inbox.html", {"threads": threads})


@login_required
def new_thread(request):
	if request.method == "POST":
		form = NewThreadForm(request.POST)
		if form.is_valid():
			thread = SupportThread.objects.create(user=request.user, subject=form.cleaned_data["subject"].strip())
			SupportMessage.objects.create(
				thread=thread,
				sender=request.user,
				from_staff=False,
				body=form.cleaned_data["message"].strip(),
			)
			thread.last_user_read_at = timezone.now()
			thread.save(update_fields=["last_user_read_at", "updated_at"])
			messages.success(request, "Message sent. We'll get back to you here.")
			return redirect("messaging:thread", thread_id=thread.pk)
	else:
		form = NewThreadForm()

	return render(request, "messaging/new_thread.html", {"form": form})


@login_required
def thread_detail(request, thread_id: int):
	thread = get_object_or_404(SupportThread, pk=thread_id, user=request.user)

	# Mark any staff replies as read by the user when they open the thread.
	thread.last_user_read_at = timezone.now()
	thread.save(update_fields=["last_user_read_at", "updated_at"])

	if request.method == "POST":
		form = ReplyForm(request.POST)
		if form.is_valid():
			SupportMessage.objects.create(
				thread=thread,
				sender=request.user,
				from_staff=False,
				body=form.cleaned_data["message"].strip(),
			)
			messages.success(request, "Reply sent.")
			return redirect("messaging:thread", thread_id=thread.pk)
	else:
		form = ReplyForm()

	return render(
		request,
		"messaging/thread_detail.html",
		{"thread": thread, "messages_list": thread.messages.select_related("sender").all(), "form": form},
	)
