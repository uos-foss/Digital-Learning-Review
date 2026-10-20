"""
Carry the Streamlit app's users and roles across to Django, so people already
known have their role and schools waiting when they first sign in with Google.

    python manage.py import_streamlit_users            # dry run, counts only
    python manage.py import_streamlit_users --apply    # write

What it reads: the shared database's `users` and `roles` tables, read-only. What
it writes: Django's own tables only (users, groups, profiles), never the shared
database.

  * Each `roles` row becomes a Group named for the role, holding the capability
    permissions the live row lists. This is the live table, not `seed_roles`'
    hard-coded map, because the two differ and the live one is what people have
    today. Grant-only, like seed_roles: it never removes a permission.
  * Each active user whose Streamlit username is an email address becomes a
    Django user (username and email the lower-cased address, no usable
    password: they sign in with Google), in their role's Group, aligned with the
    schools in the `School` cell ("All" is faculty-wide; "ECN,SPR" is two).
    Their first Google sign-in is connected to this account by
    SocialAccountAdapter.pre_social_login.
  * Someone who already has a Django account keeps it: they are added to the
    Group, and given schools only if they have none. Access is never narrowed.
  * Disabled users and legacy non-email usernames are skipped and counted.
    Per-user capability overrides are reported, not applied.

It is idempotent, so it can be run again before the cut-over to pick up what
changed in Streamlit meanwhile. By default the output is counts only; --verbose
names people.
"""

from collections import Counter

import database
from accounts import rules
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import profile_for


class Command(BaseCommand):
    help = "Create Django users and role Groups from the Streamlit users and roles tables."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Write the changes. Without it nothing is written.")
        parser.add_argument("--verbose", action="store_true",
                            help="Name the people behind each count.")
        parser.add_argument("--include-disabled", action="store_true",
                            help="Create disabled Streamlit users too, as inactive accounts.")

    def handle(self, *args, **options):
        apply = options["apply"]
        verbose = options["verbose"]
        include_disabled = options["include_disabled"]
        User = get_user_model()

        perms = {p.codename: p for p in Permission.objects.filter(
            content_type__app_label="accounts")}
        roles = database.get_roles_sqlite()
        users = database.get_users_sqlite()
        out = self.stdout.write

        out(f"{'APPLYING' if apply else 'DRY RUN (nothing written)'}: "
            f"{len(roles)} roles, {len(users)} users in the Streamlit tables.\n")

        with transaction.atomic():
            # ---- roles -> Groups -------------------------------------------------
            group_for = {}   # lower-cased role name -> Group name
            for row in roles:
                name = str(row.get("Role") or "").strip()
                if not name:
                    continue
                tokens = rules.parse_capabilities(row.get("Capabilities"))
                known = [t for t in tokens if t in perms]
                unknown = [t for t in tokens if t not in perms]
                group_for[name.lower()] = name
                group = Group.objects.filter(name=name).first()
                held = {p.codename for p in group.permissions.all()} if group else set()
                to_add = [t for t in known if t not in held]
                extra = sorted(held - set(known))
                if apply:
                    group, _ = Group.objects.get_or_create(name=name)
                    for token in to_add:
                        group.permissions.add(perms[token])
                out(f"  role {name}: {'exists' if group else 'new'}, "
                    f"grants {len(to_add)} new of {len(known)}"
                    + (f"; not a known permission: {', '.join(unknown)}" if unknown else "")
                    + (f"; Django holds extra (kept): {', '.join(extra)}" if extra else ""))

            # ---- users -> accounts -----------------------------------------------
            created = linked_existing = updated_schools = 0
            skipped_nonemail, skipped_disabled, unknown_role = [], [], []
            unknown_schools, overrides, same_email = [], [], []
            by_role, by_school = Counter(), Counter()
            seen = set()

            for row in users:
                username = str(row.get("Username") or "").strip()
                if not rules.looks_like_email(username):
                    skipped_nonemail.append(username)
                    continue
                email = username.lower()
                if email in seen:
                    same_email.append(email)
                    continue
                seen.add(email)

                active = str(row.get("Status") or "").strip().lower() == "active"
                if not active and not include_disabled:
                    skipped_disabled.append(email)
                    continue

                role = group_for.get(str(row.get("Role") or "").strip().lower())
                if role is None:
                    unknown_role.append(f"{email} ({row.get('Role')})")
                all_schools, codes, unknown = rules.parse_streamlit_schools(row.get("School"))
                if unknown:
                    unknown_schools.append(f"{email}: {', '.join(unknown)}")
                if str(row.get("Capabilities") or "").strip():
                    overrides.append(email)

                by_role[role or "(no matching role)"] += 1
                by_school["All" if all_schools else (",".join(codes) or "(none)")] += 1

                existing = User.objects.filter(email__iexact=email).first() \
                    or User.objects.filter(username__iexact=email).first()
                if existing is None:
                    created += 1
                    if not apply:
                        continue
                    user = User(username=email, email=email, is_active=active)
                    user.set_unusable_password()
                    user.save()
                    profile = profile_for(user)
                    profile.affiliation = rules.affiliation_from_email(email)
                    profile.all_schools = all_schools
                    profile.set_schools(codes)
                    profile.save()
                else:
                    linked_existing += 1
                    if not apply:
                        continue
                    user = existing
                    profile = profile_for(user)
                    if not profile.all_schools and not profile.school_list \
                            and (all_schools or codes):
                        profile.all_schools = all_schools
                        profile.set_schools(codes)
                        profile.save()
                        updated_schools += 1
                if role and apply:
                    user.groups.add(Group.objects.get(name=role))

            if not apply:
                transaction.set_rollback(True)

        # ---- report -------------------------------------------------------------
        out("")
        out(f"Accounts to create: {created}.  Already have a Django account: {linked_existing}"
            + (f" ({updated_schools} given schools)." if apply else "."))
        out(f"Skipped, disabled in Streamlit: {len(skipped_disabled)}"
            f"{' (pass --include-disabled to create them inactive)' if skipped_disabled else ''}.")
        out(f"Skipped, username is not an email address: {len(skipped_nonemail)}.")
        out("By role: " + ", ".join(f"{k} {v}" for k, v in sorted(by_role.items())))
        out("By school: " + ", ".join(f"{k} {v}" for k, v in sorted(by_school.items())))
        if unknown_role:
            out(f"No matching role in the roles table: {len(unknown_role)} "
                "(created with no Group, so no access until one is set).")
        if unknown_schools:
            out(f"School codes not in this faculty, dropped: {len(unknown_schools)}.")
        if overrides:
            out(f"Per-user capability overrides NOT applied: {len(overrides)}. "
                "Decide whether any matter before relying on this import.")
        if same_email:
            out(f"Usernames repeating an address (first kept): {len(same_email)}.")
        if verbose:
            for label, items in (("disabled", skipped_disabled),
                                 ("non-email", skipped_nonemail),
                                 ("no matching role", unknown_role),
                                 ("unknown schools", unknown_schools),
                                 ("capability overrides", overrides)):
                if items:
                    out(f"\n{label}:")
                    for item in items:
                        out(f"  {item}")
        if not apply:
            out("\nNothing was written. Re-run with --apply to make these changes.")
