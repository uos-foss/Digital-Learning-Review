For Digital Learning Advisors carrying out audits in the Audit Portal.

## The checklist and the data

### Why are some boxes already ticked when I open a module?

Because the Blackboard Template Alignment Report already answers some of the
checklist for you. Seven of the checklist's boolean items map to a template
section, and when you open a module the portal reads that section's state from
the most recent import and suggests a tick accordingly.

Hover any box for the evidence behind the suggestion: *"Last changed
14-09-2026"*, or *"Unchanged since the course was created on 01-07-2026"*. You
are never shown a tick without a reason.

The eighth item, **Learning materials structure in place**, has no template
counterpart and is never suggested on. Free-text fields are never suggested on
either.

### A section is Visible but the box isn't ticked. Is that a bug?

Usually not. Visible on its own is not enough for the four sections a module
lead owns:

* Welcome & Module Outline
* Key Staff Contacts
* Assessment Detail
* How Your Feedback Shapes this Module

For these, the portal wants the section to be **visible *and* show an edit
date**. A visible section with no edit evidence at all may well still hold the
untouched template placeholder text, and pre-ticking it would mean a section
nobody had touched looked identical to genuinely finished work.

For the three institution-owned sections that still map to a checklist item,
namely Skills Development (SGAs), Assessment Overview and Encore Lecture
Capture, Visible *is* enough. Nobody was ever expected to edit those, so
sitting untouched since course creation is their correct state, not a red flag.

### Can I untick a box the data ticked for me?

**Yes.** That is exactly what the checklist is for. If the data says a section
is visible and edited, and you go and look and find it half-finished, untick
it. Your answer is the one the portal uses from then on: on the module report,
in the Actionable Items badge, and in the school's Template Alignment figure.

### Will the next data import override my ticks?

**No.** Once you press Save Draft or Submit, your answers are the record, and
no import can change them.

It helps to think of the ticks as arriving in two stages.

**Before you've ever saved that module**, the boxes aren't really answers. They
are the portal's suggestion, redrawn from the latest import every time you open
the page. If a new report lands before you save, the suggestions simply update.
Nothing of yours is lost, because nothing of yours exists yet.

**The moment you save**, your answers are written down and the portal stops
suggesting for that module. Later imports still change the underlying data, but
the form keeps showing your answers and the dashboards keep counting your
answers.

### Does that work the other way round too?

Yes, and this is the part worth knowing. Because your answer wins permanently,
a genuine *improvement* won't show up either.

If you untick a half-finished section in October and the lead finishes it in
November, the November import will not re-tick it. The module goes on reading
"not complete" until a person opens it and changes the answer.

That is deliberate, since the alternative is data quietly contradicting an
advisor who actually went and looked. But it does mean an audited module only
moves when a human moves it. If you know a lead has acted on a finding, the
module needs revisiting rather than waiting for the next import.

### Does saving record only the box I changed?

**No. Saving records the whole form.** Every box on the page, ticked or
unticked, is written down as your answer, including ones you never looked at.

So if you go in to correct one section and hit Save, a box that was pre-ticked
by the data and that you simply left alone is now stored as your verdict,
indistinguishable from one you checked yourself, and frozen against future
imports like everything else.

In practice: when you open a module to fix one thing, glance down the rest of
the list before saving. You are signing off all of it, not just the bit you
came for.

### How do I know how fresh the suggestions are?

The tooltip on each box gives you that *section's* last-changed date, which is
not the same thing as when the report was imported. For the import date, check
the sidebar caption. Stale import, stale suggestions, on every module you open
that session.

## Drafts, submission and status

### What's the difference between Save Draft and Submit?

Both write your answers identically and both close out a spot-check. The
difference is what the module counts toward: **draft audits are excluded from
faculty compliance figures, submitted ones are included.** Submit means
"complete enough to count".

### Does submitting lock the audit?

No, and it can't. Modules are built all year, so a September audit is
legitimately out of date by January, and a spot-check on an already-submitted
module still has to be recordable. Re-saving a submitted audit revises it in
place and it stays Submitted. There is no way back to Draft, because that would
only ever mean "less complete than before". Every revision is recorded in the
**Change History** expander.

### What is "Readiness Outcome" and why is it separate from "Audit Status"?

They answer different questions:

* **Audit Status**: has a human signed this off? (Not Started / Draft /
  Submitted)
* **Readiness Outcome**: computed from the gating checklist items' current
  values. (Ready / Not Ready / Blank)

A module can read Ready without anyone having submitted it, because the
outcome is calculated from the answers rather than from the workflow stage.

## Spot-checks

### Does a new import change a spot-check I've already flagged?

No. When you flag a module, the portal freezes what the data said about it at
that moment. When the spot-check is closed out, your answers are compared
against that frozen snapshot, never against whatever the data says by then. So
a report imported in between does not move the agreement result.

### Can I close out a spot-check someone else flagged?

Yes. A flag belongs to the school it was raised in, not to the person who
raised it, so any advisor working that school sees it in their queue and can
close it. Opening it and saving a real audit response, Save Draft or Submit
whichever comes first, is what closes it. The portal records who flagged it and
who checked it separately.

### How do I reset a module I've already spot-checked?

Remove the flag from the School Dashboard's Spot-Checks tab, then re-flag it
from All Modules. Removing a checked flag also removes its agreement result,
which is why it sits behind a confirmation.

### Where do the comments I write end up?

Additional Comments are saved with the audit and turn up in three places: on
the module's own report page, under Module Checks and Readiness; in full on the
School Dashboard's Spot-Check Comments tab, for any module that was flagged for
a spot-check; and cut to a single line in the comment column of the Spot-Checks
tab next to it.

Spot-Check Comments is the one built for reading them. One card per flagged
module, most recently written first, with the module name, the flag status, and
who audited and flagged it. There is a search box across module codes and
comment text, a filter for checked or pending flags, and a CSV export. A
flagged module nobody has audited yet has nothing to show, so those are hidden
unless you tick the box to include them.

What appears there is the module's current answer, not a copy taken when the
flag was closed. Revise the audit and the comment changes with it.

### Are those comments private to advisors?

No. Write them for the module lead, because the module lead reads them: the
comment appears on their own Module report page, and school leadership can read
it on the School Dashboard. The internal-only notes field the portal used to
have was removed, so there is no advisor-only box any more.

Say what is outstanding and what would resolve it, rather than leaving a note
to yourself.

## Counts and badges

### A module I've never audited shows items outstanding on its page but nothing on the dashboard badge. Why?

Deliberate. Around 1,560 of roughly 1,570 modules have never been audited. If
every unaudited module counted all eight checklist items as outstanding, the
Actionable Items badge would be a constant rather than something that tells you
where to look.

So for a module with no audit trail at all, only the data-driven findings from
Leganto, Ally and template readiness reach the badge. The module's own page
still shows the full worklist once you open it. Quiet badge, full list on
opening.

### What counts toward Actionable Items?

Everything still outstanding across every source: checklist answers, reading
lists, accessibility, and template sections. It is computed in one place, so
the badge on the dashboard and the Actions panel on the module report cannot
disagree about what a module has outstanding.
