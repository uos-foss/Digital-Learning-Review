"""
Managing accounts without the shell.

The README told people to set a school alignment "in the Django admin" while
nothing was registered there, which was wrong twice over: the page did not
exist, and the first person to sign in with Google lands with no alignment and
is refused every module until someone changes that. This is the page that
makes it a two-minute job instead of a shell command.

Alignment is shown on the user list too, because the question being asked is
almost always "why can this person not see anything", and the answer is
usually visible from that list.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

import processing

from accounts.models import Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0
    fields = ("affiliation", "affiliation_is_manual", "all_schools", "schools")
    help_texts = {"schools": "Comma-separated codes, e.g. EDC,ALA."}

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form.base_fields["schools"].help_text = (
            "Comma-separated school codes from "
            f"{', '.join(processing.FACULTY_SCHOOLS)}. Unknown codes are dropped "
            "on save. Ignored when 'all schools' is ticked.")
        return formset


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "affiliation", "affiliation_is_manual",
                    "all_schools", "schools")
    list_filter = ("affiliation", "affiliation_is_manual", "all_schools")
    search_fields = ("user__username", "user__email", "schools")

    def save_model(self, request, obj, form, change):
        # Normalise through the same rule the scoping check reads, so a typo
        # in this box cannot produce an alignment that matches nothing.
        obj.set_schools(obj.schools.split(","))
        super().save_model(request, obj, form, change)


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "email", "is_staff", "roles", "access")

    @admin.display(description="Roles")
    def roles(self, user):
        return ", ".join(g.name for g in user.groups.all()) or "-"

    @admin.display(description="Sees")
    def access(self, user):
        """What this account can actually reach, in one column."""
        if user.is_superuser or user.has_perm("accounts.view_all"):
            return "every school"
        profile = getattr(user, "profile", None)
        if profile and profile.all_schools:
            return "every school"
        schools = profile.school_list if profile else []
        return ", ".join(schools) if schools else "nothing yet"


admin.site.unregister(User)
admin.site.register(User, UserAdmin)

admin.site.site_header = "Digital Learning Review platform"
admin.site.site_title = "DLR platform"
