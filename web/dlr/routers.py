"""
Database router: the `auditdata` app reads the shared audit database, and
everything else uses Django's own.

The hard rule is `allow_migrate`: Django must never create, alter or drop a
table in the shared database. The Streamlit app owns that schema
(`database.py`), and the AI-Audit app reads it too. A stray migration there
would be the worst kind of bug this split exists to prevent.
"""

AUDIT_APP = "auditdata"
AUDIT_DB = "audit"


class AuditRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_label == AUDIT_APP:
            return AUDIT_DB
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == AUDIT_APP:
            return AUDIT_DB
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Relations within one database are fine; across the two are not.
        labels = {obj1._meta.app_label, obj2._meta.app_label}
        if labels == {AUDIT_APP}:
            return True
        if AUDIT_APP in labels:
            return False
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == AUDIT_APP:
            # Never migrate the shared schema, in either database.
            return False
        if db == AUDIT_DB:
            # And never put Django's own tables in the shared file.
            return False
        return None
