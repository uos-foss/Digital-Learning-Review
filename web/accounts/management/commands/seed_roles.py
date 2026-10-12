"""
Create the roles as Groups, holding the capabilities as permissions.

The map below is the one in data_manager.py's seed defaults, with one
correction already made there: **ML does not hold edit_checklist.** Audits are
carried out by Digital Learning Advisors on the module lead's behalf, so a
lead holding the audit capability was a bug that kept being reintroduced by
hand because the old defaults shipped it. See CLAUDE.md, "Who does what".

Add-only, deliberately. It creates missing groups and grants missing
permissions, and never takes one away: an admin may have granted something on
purpose (view_sga_analytics is the obvious one, which nothing seeds), and a
command run during a deployment should not quietly revoke it. Re-running is
safe.
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

ROLE_CAPABILITIES = {
    "admin": ["view_all", "edit_checklist", "access_admin_panel", "view_school_dashboard"],
    "DLA": ["view_all", "edit_checklist", "view_school_dashboard"],
    "FOSS": ["view_all", "view_school_dashboard"],
    "ML": ["view_school", "report_fixed"],
    "SA": ["view_school", "view_school_dashboard"],
    "SL": ["view_school", "view_school_dashboard"],
}


class Command(BaseCommand):
    help = "Create or update the role Groups and their capability permissions."

    def handle(self, *args, **options):
        perms = {p.codename: p for p in Permission.objects.filter(
            content_type__app_label="accounts")}

        missing = {c for caps in ROLE_CAPABILITIES.values() for c in caps} - set(perms)
        if missing:
            raise SystemExit(
                f"These capabilities are not permissions on accounts.Profile: "
                f"{', '.join(sorted(missing))}. Add them to Profile.Meta.permissions "
                f"and run migrate first.")

        for role, capabilities in ROLE_CAPABILITIES.items():
            group, created = Group.objects.get_or_create(name=role)
            held = {p.codename for p in group.permissions.all()}
            granted = [c for c in capabilities if c not in held]
            for codename in granted:
                group.permissions.add(perms[codename])

            extra = sorted(held - set(capabilities))
            state = "created" if created else "exists"
            self.stdout.write(
                f"  {role:<6} {state:<8} "
                f"granted: {', '.join(granted) if granted else 'nothing new'}"
                + (f"  (also holds: {', '.join(extra)})" if extra else ""))

        self.stdout.write(self.style.SUCCESS(
            f"{len(ROLE_CAPABILITIES)} roles present. Nothing was revoked."))
