"""
Models over tables the Streamlit app owns. Every one is `managed = False`, and
the router refuses to migrate this app, so Django can read and write rows but
can never touch the schema.

Only the tables the spike needs are modelled. Two tables are deliberately
absent:

- `sits_assessment_2026_27` has no primary key (SITS rows are one per
  assessment component and the table is replaced wholesale), and Django
  requires one. It is read with pandas in modules/loaders.py instead, which is
  also how the Streamlit app reads it. The year in the table name is a
  contract with the AI-Audit app, so it cannot simply be renamed.
- The Ally, Leganto, readiness and SGA tables are read through the existing
  `database.py` helpers, which already return the aggregated frames every
  view needs. Re-modelling them here would duplicate that work.

Writes still go through `database.save_audit_response()` during the
transition, so both front ends record an audit identically. These models are
for reading.
"""

from django.db import models


class AuditField(models.Model):
    """A checklist question. `audit_fields` in the shared database."""

    id = models.TextField(primary_key=True)
    label = models.TextField(blank=True, null=True)
    action_label = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    field_type = models.TextField(blank=True, null=True)
    is_active = models.IntegerField(default=1)
    display_order = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "audit_fields"
        ordering = ["display_order"]

    def __str__(self):
        return self.label or self.id


class AuditResponse(models.Model):
    """
    One answer for one module and field. `audit_responses` has a composite
    primary key (module_code, field_id), which Django does not support, so
    module_code stands in as the pk for reads. Never write through this model:
    use database.save_audit_response(), which also writes the history row.
    """

    module_code = models.TextField(primary_key=True)
    field_id = models.TextField()
    value = models.TextField(blank=True, null=True)
    auditor_username = models.TextField(blank=True, null=True)
    timestamp = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "audit_responses"

    def __str__(self):
        return f"{self.module_code}/{self.field_id}"
