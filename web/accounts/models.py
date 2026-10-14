"""
What the platform knows about an account beyond Google's say-so.

Two things live here that the Streamlit app has nowhere to put:

1. **Which schools a person is actually aligned with.** The `users` table has
   one School column, and real DLA accounts are provisioned 'All' for
   practical reasons even when the person works with two specific schools, so
   today the schema simply cannot express it. See CLAUDE.md, "Spot-check
   flagging".
2. **Affiliation**, staff or student, which Google does not tell us. It is
   stored rather than worked out at the point of use, so that when
   institutional SSO arrives its claim fills the same field and nothing
   downstream changes.

Capabilities are Django permissions on this model (see Meta.permissions), and
roles are Groups holding them: `manage.py seed_roles` creates both. A
permission check is then `user.has_perm("accounts.edit_checklist")`, and a
superuser passes every one of them, which is what keeps the local admin
account working when Google does not.
"""

from django.conf import settings
from django.db import models

from accounts import rules


class Profile(models.Model):
    """One row per account, created automatically. Lives in Django's own
    database, never in the shared audit database."""

    AFFILIATION_CHOICES = [
        (rules.STAFF, "Staff"),
        (rules.STUDENT, "Student"),
        (rules.UNKNOWN, "Unknown"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")

    affiliation = models.CharField(
        max_length=16, choices=AFFILIATION_CHOICES, default=rules.UNKNOWN)

    affiliation_is_manual = models.BooleanField(
        default=False,
        help_text="Set by a person, so sign-in must stop guessing and leave it alone.")

    all_schools = models.BooleanField(
        default=False,
        help_text="Faculty-wide access, for DLAs and admins. Overrides the school list.")

    schools = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Comma-separated school codes, e.g. 'EDC,ALA'. Ignored when "
                  "all_schools is set.")

    class Meta:
        permissions = [
            # The capability tokens the Streamlit app already uses, as
            # permissions. Same names deliberately: an account's capabilities
            # should read the same in both front ends while both exist.
            ("view_all", "See every school's data"),
            ("view_school", "Scoped to their own school(s)"),
            ("view_school_dashboard", "Reach the School Dashboard"),
            ("edit_checklist", "Carry out audits"),
            ("access_admin_panel", "Full admin"),
            ("access_admin_limited", "Limited admin"),
            ("view_sga_analytics", "See SGA counts and attributes"),
            ("report_fixed", "Report a section as fixed"),
        ]

    def __str__(self):
        return f"{self.user.username} ({self.affiliation})"

    # -- schools ---------------------------------------------------------

    @property
    def school_list(self):
        """The alignment as a list of codes, cleaned against FACULTY_SCHOOLS."""
        return rules.normalise_schools(self.schools.split(","))

    def set_schools(self, codes):
        """Replace the alignment. Unknown codes are dropped, not stored."""
        self.schools = ",".join(rules.normalise_schools(codes))

    # -- what they may see -----------------------------------------------

    def may_view_module(self, code):
        return rules.may_view_module(code, self.all_schools, self.school_list)

    def may_view_school(self, school):
        return rules.may_view_school(school, self.all_schools, self.school_list)


def profile_for(user):
    """
    The profile for a user, created if missing.

    Accounts can appear without passing through sign-in (createsuperuser, the
    Django admin, a fixture), so no view should assume the row exists.
    """
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile


def may_view_module(user, code):
    """
    Whether this user may see this module.

    `view_all` wins outright, which is how DLAs and admins work today. A
    superuser passes because Django grants every permission to one, so the
    break-glass account is never locked out of a page.
    """
    if not user.is_authenticated:
        return False
    if user.has_perm("accounts.view_all"):
        return True
    return profile_for(user).may_view_module(code)


def capabilities_of(user):
    """
    The user's capability tokens, in the lowercase form `processing.py` reads
    (`can_view_sga()` and friends take the same list the Streamlit session
    holds). Read from the permissions, so a superuser has every one.
    """
    if not user.is_authenticated:
        return []
    return [codename for codename, _ in Profile._meta.permissions
            if user.has_perm(f"accounts.{codename}")]


def has_basic_school_view(user):
    """
    Whether this account gets the basic school page: the modules list and
    nothing else. That is anyone without `view_school_dashboard`, which is how
    a module lead is told apart from the DLA tool's users (ML holds
    `view_school` only). A superuser holds every permission, so is never basic.
    """
    return user.is_authenticated and not user.has_perm("accounts.view_school_dashboard")


def may_view_school(user, school):
    """Whether this user may see this school: `view_all` wins outright, as in
    may_view_module(), otherwise the school must be on their alignment."""
    if not user.is_authenticated:
        return False
    if user.has_perm("accounts.view_all"):
        return True
    return profile_for(user).may_view_school(school)
