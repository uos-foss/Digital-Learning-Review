"""
Who allauth is allowed to let in.

Two refusals, both deliberate:

1. **No self-service password accounts.** Sign-in is Google, plus whatever
   local accounts an admin creates on purpose. An open signup form on a tool
   holding audit data would be a gift.
2. **University accounts only**, checked server side against the email Google
   says it verified.

On the second: the provider is configured with Google's `hd` parameter, which
makes the account chooser prefer university accounts. That is a convenience,
not a control. `hd` is a request parameter, the person signing in controls
their own browser, and a personal account can reach the callback anyway. The
check that actually holds is the one below, against `email_verified` and the
address itself.
"""

import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.shortcuts import render

from accounts import rules

logger = logging.getLogger(__name__)


def allowed_domain():
    return getattr(settings, "ALLOWED_EMAIL_DOMAIN", rules.ALLOWED_EMAIL_DOMAIN)


class AccountAdapter(DefaultAccountAdapter):
    """Local password accounts exist, but only an admin may create one."""

    def is_open_for_signup(self, request):
        return False


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Google sign-in, restricted to verified university addresses."""

    def is_open_for_signup(self, request, sociallogin):
        # A first Google sign-in creates the account. The domain check in
        # pre_social_login has already run by this point, so anyone reaching
        # here holds a verified university address.
        return True

    def pre_social_login(self, request, sociallogin):
        """
        Runs after Google has authenticated someone and before allauth decides
        what to do with them, which is the only place to refuse an otherwise
        valid login.
        """
        extra = sociallogin.account.extra_data or {}
        email = (sociallogin.user.email or extra.get("email") or "").strip()

        # Google reports whether it verified the address. An unverified one
        # proves nothing about who owns it, so the domain check would be
        # meaningless: refuse rather than trust it.
        verified = extra.get("email_verified")
        if verified is False or (verified is None and not email):
            logger.warning("Refused Google sign-in with no verified email address")
            raise ImmediateHttpResponse(self._refuse(request, email, "unverified"))

        if not rules.is_allowed_domain(email, allowed_domain()):
            logger.warning("Refused Google sign-in for %s (not %s)", email, allowed_domain())
            raise ImmediateHttpResponse(self._refuse(request, email, "domain"))

    def _refuse(self, request, email, reason):
        return render(request, "accounts/refused.html", {
            "email": email,
            "reason": reason,
            "domain": allowed_domain(),
        }, status=403)
