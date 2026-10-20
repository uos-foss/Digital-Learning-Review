"""
The sign-in and scoping rules, pinned down.

These decide who gets in and what they can see, so they are the rules where a
quiet mistake costs most. They live in web/accounts/rules.py with no Django in
them precisely so they can be tested here, next to the findings tests, rather
than only through a request.

Run from the repo root:

    .venv/Scripts/python -m pytest
"""

import processing

from accounts import rules


class TestAllowedDomain:
    """Who may sign in at all. Google's `hd` parameter is a hint to the
    account chooser and is set by the client, so this check is the one that
    actually holds (see accounts/adapters.py)."""

    def test_university_address_allowed(self):
        assert rules.is_allowed_domain("a.person@sheffield.ac.uk") is True

    def test_case_and_whitespace_ignored(self):
        assert rules.is_allowed_domain("  A.Person@Sheffield.AC.UK  ") is True

    def test_personal_account_refused(self):
        assert rules.is_allowed_domain("someone@gmail.com") is False

    def test_lookalike_domain_refused(self):
        """The reason this is an exact match and not `endswith`."""
        assert rules.is_allowed_domain("a@notsheffield.ac.uk") is False

    def test_suffix_attack_refused(self):
        """A domain that merely starts with ours is not ours."""
        assert rules.is_allowed_domain("a@sheffield.ac.uk.example.com") is False

    def test_subdomain_refused(self):
        """Deliberately not accepted. If one is ever needed, add it explicitly
        rather than loosening the match for everything."""
        assert rules.is_allowed_domain("a@mail.sheffield.ac.uk") is False

    def test_nonsense_refused(self):
        for value in ("", None, "not-an-email", "@", "a@"):
            assert rules.is_allowed_domain(value) is False


class TestAffiliationGuess:
    """A default a person can correct, never a fact. The pattern here is a
    placeholder for the one GPLdash already uses."""

    def test_digits_read_as_student(self):
        assert rules.affiliation_from_email("ab1cd23@sheffield.ac.uk") == rules.STUDENT

    def test_no_digits_reads_as_staff(self):
        assert rules.affiliation_from_email("a.n.other@sheffield.ac.uk") == rules.STAFF

    def test_no_address_is_unknown_not_a_guess(self):
        for value in ("", None, "no-at-sign"):
            assert rules.affiliation_from_email(value) == rules.UNKNOWN

    def test_digits_in_the_domain_do_not_count(self):
        """Only the local part is evidence about the person."""
        assert rules.affiliation_from_email("a.person@sheffield1.ac.uk") == rules.STAFF


class TestNormaliseSchools:
    def test_unknown_codes_are_dropped(self):
        """A typo must narrow what someone sees, never widen it."""
        assert rules.normalise_schools(["EDC", "ZZZ"]) == ["EDC"]

    def test_case_and_whitespace_cleaned(self):
        assert rules.normalise_schools([" edc ", "ala"]) == ["EDC", "ALA"]

    def test_duplicates_collapse_and_order_holds(self):
        assert rules.normalise_schools(["ALA", "EDC", "ALA"]) == ["ALA", "EDC"]

    def test_nothing_in_nothing_out(self):
        assert rules.normalise_schools(None) == []
        assert rules.normalise_schools([]) == []

    def test_every_faculty_school_survives(self):
        assert rules.normalise_schools(processing.FACULTY_SCHOOLS) == list(
            processing.FACULTY_SCHOOLS)


class TestMayView:
    def test_faculty_wide_sees_everything(self):
        assert rules.may_view_school("EDC", True, []) is True
        assert rules.may_view_module("EDC004", True, []) is True

    def test_own_school_only(self):
        assert rules.may_view_module("EDC004", False, ["EDC"]) is True
        assert rules.may_view_module("ALA102", False, ["EDC"]) is False

    def test_more_than_one_alignment(self):
        """A DLA can cover two schools, which the users table cannot express
        today: see CLAUDE.md on faculty-wide provisioning."""
        for code in ("EDC004", "ALA102"):
            assert rules.may_view_module(code, False, ["EDC", "ALA"]) is True

    def test_no_alignment_sees_nothing(self):
        assert rules.may_view_module("EDC004", False, []) is False

    def test_messy_code_still_resolves(self):
        """school_of() normalises, so a padded or lowercase code must not
        quietly fail the check."""
        assert rules.may_view_module(" edc004 ", False, ["EDC"]) is True

    def test_out_of_faculty_code_sees_nothing(self):
        """A code whose prefix belongs to no school in this faculty cannot be
        matched by any alignment."""
        assert rules.may_view_module("SCS101", False, ["EDC"]) is False


# -- importing the Streamlit users table ---------------------------------

def test_streamlit_school_cells():
    """One code, a comma list, and 'All' (faculty-wide), whatever the case or
    spacing. Unknown codes are reported and never kept."""
    assert rules.parse_streamlit_schools("All") == (True, [], [])
    assert rules.parse_streamlit_schools(" all ") == (True, [], [])
    assert rules.parse_streamlit_schools("ECN,SPR") == (False, ["ECN", "SPR"], [])
    assert rules.parse_streamlit_schools("ecn, spr ,ECN") == (False, ["ECN", "SPR"], [])
    assert rules.parse_streamlit_schools("EDC") == (False, ["EDC"], [])
    assert rules.parse_streamlit_schools("EDC;GPL") == (False, ["EDC", "GPL"], [])
    assert rules.parse_streamlit_schools("EDC,XYZ") == (False, ["EDC"], ["XYZ"])
    assert rules.parse_streamlit_schools("") == (False, [], [])
    assert rules.parse_streamlit_schools(None) == (False, [], [])
    # "All" beside a school is still faculty-wide.
    assert rules.parse_streamlit_schools("EDC,All") == (True, [], [])


def test_streamlit_capability_cells():
    assert rules.parse_capabilities("view_all, View_School ,edit_checklist") == [
        "view_all", "view_school", "edit_checklist"]
    assert rules.parse_capabilities("view_all,view_all") == ["view_all"]
    assert rules.parse_capabilities("") == []
    assert rules.parse_capabilities(None) == []


def test_which_streamlit_usernames_are_email_addresses():
    assert rules.looks_like_email("A.Person@Sheffield.ac.uk")
    assert not rules.looks_like_email("admin")
    assert not rules.looks_like_email("someone@")
    assert not rules.looks_like_email("@sheffield.ac.uk")
    assert not rules.looks_like_email("two words@sheffield.ac.uk")
    assert not rules.looks_like_email(None)
