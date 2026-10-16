from arches_abac_permissions.models import InclusionRule


class NoChecksRule(InclusionRule):
    """A rule class that keeps the base validate_definition, for testing clean()."""

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
