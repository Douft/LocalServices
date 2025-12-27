from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from django.db.models.manager import RelatedManager


class SupportThreadStatus(models.TextChoices):
	OPEN = "open", "Open"
	CLOSED = "closed", "Closed"


class SupportThread(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="support_threads")
	subject = models.CharField(max_length=120)
	status = models.CharField(max_length=16, choices=SupportThreadStatus.choices, default=SupportThreadStatus.OPEN)

	last_user_read_at = models.DateTimeField(null=True, blank=True)
	last_staff_read_at = models.DateTimeField(null=True, blank=True)
	last_message_at = models.DateTimeField(null=True, blank=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at"]
		indexes = [
			models.Index(fields=["status", "updated_at"]),
			models.Index(fields=["user", "updated_at"]),
		]

	def __str__(self) -> str:
		return f"{self.subject} ({self.user.pk})"

	# Help type checkers understand our related_name.
	messages: "RelatedManager[SupportMessage]"

	def mark_user_read(self) -> None:
		self.last_user_read_at = timezone.now()
		self.save(update_fields=["last_user_read_at", "updated_at"])

	def mark_staff_read(self) -> None:
		self.last_staff_read_at = timezone.now()
		self.save(update_fields=["last_staff_read_at", "updated_at"])

	@property
	def has_unread_for_user(self) -> bool:
		cutoff = self.last_user_read_at
		qs = self.messages.filter(from_staff=True)
		if cutoff:
			qs = qs.filter(created_at__gt=cutoff)
		return qs.exists()

	@property
	def has_unread_for_staff(self) -> bool:
		cutoff = self.last_staff_read_at
		qs = self.messages.filter(from_staff=False)
		if cutoff:
			qs = qs.filter(created_at__gt=cutoff)
		return qs.exists()


class SupportMessage(models.Model):
	thread = models.ForeignKey(SupportThread, on_delete=models.CASCADE, related_name="messages")
	sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
	from_staff = models.BooleanField(default=False)
	body = models.TextField()
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["created_at"]
		indexes = [
			models.Index(fields=["thread", "created_at"]),
			models.Index(fields=["from_staff", "created_at"]),
		]

	def __str__(self) -> str:
		return f"Message {self.pk}"

	def save(self, *args, **kwargs):
		is_new = self.pk is None
		super().save(*args, **kwargs)
		if is_new:
			SupportThread.objects.filter(pk=self.thread.pk).update(last_message_at=self.created_at)
