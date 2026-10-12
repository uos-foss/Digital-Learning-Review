"""
Keeping a profile beside every account, and filling in what sign-in can tell us.

The affiliation guess runs once, at first sign-in, and never again: it is a
default to be corrected, and re-running it on every login would quietly undo
a correction someone made by hand. `affiliation_is_manual` is what records
that a person has had their say.
"""

import logging

from allauth.account.signals import user_signed_up
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts import rules
from accounts.models import Profile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    """Every account gets a profile, however it was created."""
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(user_signed_up)
def set_affiliation_on_signup(request, user, **kwargs):
    """
    A first sign-in guesses staff or student from the address.

    Only on signup, and only when nobody has set it by hand. The guess is
    recorded with affiliation_is_manual left False, so it is visibly a guess
    in the admin rather than something that looks authoritative.
    """
    profile, _ = Profile.objects.get_or_create(user=user)
    if profile.affiliation_is_manual:
        return
    profile.affiliation = rules.affiliation_from_email(user.email)
    profile.save(update_fields=["affiliation"])
    logger.info("New account %s recorded as %s (guessed from the address)",
                user.username, profile.affiliation)
