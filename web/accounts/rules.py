"""
Sign-in and scoping decisions, with no Django in them.

These are the rules that decide who may sign in, what they are taken to be,
and which modules they may see. They are kept importable without Django (and
without Streamlit) for the same reason processing.py is: a rule that can only
run inside a request is a rule that cannot be tested, and these are the ones
most likely to be wrong in a way nobody notices.

Tested from tests/ at the repo root.
"""

import re

import processing

# Only university accounts may sign in. Google's `hd` parameter is a hint to
# the account chooser, not a guarantee: it is set by the client and the
# response can be replayed, so the domain is checked here, server side,
# against the email Google says it verified. Never rely on `hd` alone.
ALLOWED_EMAIL_DOMAIN = "sheffield.ac.uk"

# A placeholder for the rule GPLdash already uses, which should be copied here
# rather than reinvented. Local parts containing a digit are taken to be
# students (ab1cd23), those without to be staff (a.n.other). It is wrong often
# enough to matter - postgraduate researchers, staff who are also students,
# visitors, honorary contracts - which is why affiliation is stored on the
# account and can be set by hand. See STAFF/STUDENT/UNKNOWN below.
STUDENT_LOCAL_PART = re.compile(r"\d")

STAFF = "staff"
STUDENT = "student"
UNKNOWN = "unknown"


def email_domain(email):
    """The domain part of an email address, lowercased. '' if there isn't one."""
    _, _, domain = str(email or "").strip().lower().rpartition("@")
    return domain


def is_allowed_domain(email, domain=ALLOWED_EMAIL_DOMAIN):
    """
    Whether this address belongs to the university.

    An exact domain match, not a suffix match: `notsheffield.ac.uk` and
    `sheffield.ac.uk.example.com` both end in the right letters and neither is
    the university. Subdomains are deliberately not accepted either; if one is
    ever needed it should be added explicitly.
    """
    return email_domain(email) == str(domain or "").strip().lower()


def affiliation_from_email(email):
    """
    A guess at staff or student from the address alone, or UNKNOWN when there
    is no address to guess from.

    This is the weakest part of the design and is meant to be: without an
    affiliation claim from institutional SSO there is nothing better to go on.
    Treat the result as a default that a human can correct, never as a fact,
    and never gate anything that matters on it alone.
    """
    local, _, domain = str(email or "").strip().lower().partition("@")
    if not local or not domain:
        return UNKNOWN
    return STUDENT if STUDENT_LOCAL_PART.search(local) else STAFF


def normalise_schools(codes):
    """
    Clean a list of school codes down to the ones this faculty actually has,
    uppercased and deduplicated, order preserved.

    Unknown codes are dropped rather than kept: a typo in someone's alignment
    should narrow what they see, never widen it, and a code that matches no
    school would silently match no modules anyway.
    """
    seen, out = set(), []
    for code in codes or []:
        school = str(code or "").strip().upper()
        if school in processing.FACULTY_SCHOOLS and school not in seen:
            seen.add(school)
            out.append(school)
    return out


def may_view_school(school, all_schools, assigned):
    """Whether someone aligned with `assigned` may see this school's data."""
    if all_schools:
        return True
    return str(school or "").strip().upper() in set(normalise_schools(assigned))


def may_view_module(code, all_schools, assigned):
    """
    The same question for one module code.

    The school comes from processing.school_of(), the one place the
    code-prefix rule lives, so scoping cannot disagree with the rest of the
    app about which school a module belongs to.
    """
    return may_view_school(processing.school_of(code), all_schools, assigned)
