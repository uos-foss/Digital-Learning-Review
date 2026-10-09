from django.apps import AppConfig


class AuditDataConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "auditdata"
    verbose_name = "Shared audit database (read-only schema)"
