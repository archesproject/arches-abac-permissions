from django.core.management.base import BaseCommand

from arches_abac_permissions.models import InclusionRule
from arches_abac_permissions.reindex import reindex_resources, rule_matches


class Command(BaseCommand):
    help = "Re-index the resources the given inclusion rules match."

    def add_arguments(self, parser):
        parser.add_argument("rule_ids", nargs="+")

    def handle(self, *args, **options):
        rules = InclusionRule.objects.filter(pk__in=options["rule_ids"])
        ids = set().union(*(rule_matches(rule) for rule in rules))
        reindex_resources(ids)
        self.stdout.write(f"Re-indexed {len(ids)} resources for {len(rules)} rules.")
