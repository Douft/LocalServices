from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import UserProfile

User = get_user_model()


class UserProfileInline(admin.StackedInline):
	model = UserProfile
	can_delete = False
	extra = 0


try:
	admin.site.unregister(User)
except admin.sites.NotRegistered:
	pass


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
	inlines = [UserProfileInline]
