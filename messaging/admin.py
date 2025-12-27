from __future__ import annotations

from django.contrib import admin
from django.utils import timezone

from .models import SupportMessage, SupportThread


class SupportMessageInline(admin.TabularInline):
	model = SupportMessage
	extra = 1
	fields = ("created_at", "from_staff", "sender", "body")
	readonly_fields = ("created_at", "from_staff", "sender")

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(SupportThread)
class SupportThreadAdmin(admin.ModelAdmin):
	list_display = ("id", "subject", "user", "status", "last_message_at", "unread_for_staff")
	list_filter = ("status",)
	search_fields = ("subject", "user__username", "user__email")
	ordering = ("-updated_at",)
	inlines = [SupportMessageInline]
	readonly_fields = ("created_at", "updated_at", "last_message_at")
	fields = ("user", "subject", "status", "last_user_read_at", "last_staff_read_at", "last_message_at", "created_at", "updated_at")

	def get_queryset(self, request):
		qs = super().get_queryset(request)
		return qs.select_related("user")

	def unread_for_staff(self, obj: SupportThread):
		return "Yes" if obj.has_unread_for_staff else ""
	unread_for_staff.short_description = "Unread"

	def save_formset(self, request, form, formset, change):
		instances = formset.save(commit=False)
		for inst in instances:
			if isinstance(inst, SupportMessage):
				# Any message created via admin is a staff reply.
				inst.from_staff = True
				inst.sender = request.user
			inst.save()
		formset.save_m2m()

		# Mark as read by staff when staff interacts.
		obj = form.instance
		obj.last_staff_read_at = timezone.now()
		obj.save(update_fields=["last_staff_read_at", "updated_at"])

	def change_view(self, request, object_id, form_url="", extra_context=None):
		resp = super().change_view(request, object_id, form_url=form_url, extra_context=extra_context)
		try:
			SupportThread.objects.filter(pk=object_id).update(last_staff_read_at=timezone.now())
		except Exception:
			pass
		return resp
