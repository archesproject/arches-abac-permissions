from functools import reduce
from itertools import chain
from operator import and_, or_

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from arches.app.models.models import ResourceInstance
from arches.app.search.elasticsearch_dsl_builder import Bool
from arches_abac_permissions.models import InclusionRule
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    has_clauses,
)
from arches_abac_permissions.rule_types import RuleType, get_rule_type_for_rule

AND = "and"
OR = "or"


class CombinedRule(InclusionRule):
    """
    Rule combining other rules, in groups that may nest.

    definition: a group, where a group is
        {"operator": "and" | "or", "rule_ids": ["<rule id>", ...],
         "groups": [<group>, ...], "exclude_rule_ids": ["<rule id>", ...]}

    A group matches resources matched by all ("and") or any ("or") of its
    rules and groups, less those matched by any of its excluded rules. A
    combined rule may include other combined rules, but not itself, directly
    or indirectly. Included rules are evaluated whether or not they are
    active. A rule that fails to evaluate fails the whole combination, so a
    broken exclusion can never widen access.
    """

    rule_type = RuleType(
        key="combined",
        label=gettext_lazy("Combination of Rules"),
        description=gettext_lazy(
            "Matches resources matched by all or any of other rules, "
            "except those matched by excluded rules"
        ),
        icon="pi pi-sitemap",
        definition_keys=("operator", "rule_ids", "groups", "exclude_rule_ids"),
    )

    @classmethod
    def clean_definition(cls, raw_definition, definition_keys):
        return clean_group(raw_definition)

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        return False

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        return ResourceInstance.objects.filter(
            combine_parts(
                inclusion_rule.definition,
                cls.load_rules(inclusion_rule.definition),
                lambda rule: Q(pk__in=rule.get_matching_resources().values("pk")),
                combine_queries,
            )
        )

    @classmethod
    def get_search_filter(cls, inclusion_rule):
        return combine_parts(
            inclusion_rule.definition,
            cls.load_rules(inclusion_rule.definition),
            search_filter_or_none,
            combine_search_filters,
        )

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        return combine_parts(
            inclusion_rule.definition,
            cls.load_rules(inclusion_rule.definition),
            lambda rule: rule.matches_resource(resource),
            combine_matches,
        )

    @classmethod
    def validate_definition(cls, inclusion_rule):
        if str(inclusion_rule.pk) in cls.load_rules(inclusion_rule.definition):
            raise ValidationError(_("A combined rule cannot include itself."))

    @classmethod
    def load_rules(cls, definition):
        """
        Validate the definition and return, by id, every rule it reaches,
        including the parts of the combined rules it includes.
        """
        check_group(definition)
        rules = {}
        wanted = {str(pk) for pk in rule_ids_in(definition)}
        while wanted:
            try:
                loaded = {
                    str(rule.pk): rule
                    for rule in InclusionRule.objects.filter(pk__in=wanted)
                }
            except ValidationError:
                raise ValidationError(_("Rule ids must be UUIDs."))
            missing = wanted - loaded.keys()
            if missing:
                raise ValidationError(
                    _("No rule exists with id %(ids)s.")
                    % {"ids": ", ".join(sorted(missing))}
                )
            rules.update(loaded)
            wanted = set()
            for rule in loaded.values():
                rule_type = get_rule_type_for_rule(rule.modulename, rule.classname)
                # Untyped rules (Search, QuerySet) aren't evaluated, so as an
                # exception they would exclude nothing.
                if rule_type is None or not rule_type.available:
                    raise ValidationError(
                        _("Rule %(name)s can't be part of a combination.")
                        % {"name": rule.name}
                    )
                if rule.classname == cls.__name__:
                    check_group(rule.definition)
                    wanted |= {str(pk) for pk in rule_ids_in(rule.definition)}
            wanted -= rules.keys()
        return rules

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"


def clean_group(raw):
    return {
        "operator": str(raw.get("operator", "")),
        "rule_ids": [str(pk) for pk in raw.get("rule_ids") or []],
        # Anything else is kept as sent, so check_group refuses it.
        "groups": [
            clean_group(group) if isinstance(group, dict) else group
            for group in raw.get("groups") or []
        ],
        "exclude_rule_ids": [str(pk) for pk in raw.get("exclude_rule_ids") or []],
    }


def check_group(group):
    if not isinstance(group, dict):
        raise ValidationError(_("Each group must be an object."))
    if group.get("operator") not in (AND, OR):
        raise ValidationError(_("The operator must be 'and' or 'or'."))
    for key in ("rule_ids", "groups", "exclude_rule_ids"):
        if not isinstance(group.get(key, []), list):
            raise ValidationError(_("'%s' must be a list.") % key)
    if not group.get("rule_ids") and not group.get("groups"):
        raise ValidationError(_("Each group needs at least one rule or group."))
    for child in group.get("groups", []):
        check_group(child)


def rule_ids_in(group):
    """Every rule id in a group and its subgroups, for a checked or stored group."""
    if not isinstance(group, dict):
        return []
    ids = [*group.get("rule_ids", []), *group.get("exclude_rule_ids", [])]
    for child in group.get("groups", []):
        ids += rule_ids_in(child)
    return ids


IN_PROGRESS = object()


def combine_parts(group, rules, evaluate, combine, results=None):
    """
    Combine a group's parts with ``combine``, evaluating each rule once with
    ``evaluate`` and following included combined rules through ``rules``.
    """
    results = {} if results is None else results

    def part(pk):
        pk = str(pk)
        if results.get(pk) is IN_PROGRESS:
            raise ValidationError(_("A combined rule cannot include itself."))
        if pk not in results:
            results[pk] = IN_PROGRESS
            rule = rules[pk]
            if rule.classname == CombinedRule.__name__:
                results[pk] = combine_parts(
                    rule.definition, rules, evaluate, combine, results
                )
            else:
                results[pk] = evaluate(rule)
        return results[pk]

    # Generators, so "and" and "or" stop at the first part that decides them.
    included = chain(
        (part(pk) for pk in group.get("rule_ids", [])),
        (
            combine_parts(child, rules, evaluate, combine, results)
            for child in group.get("groups", [])
        ),
    )
    excluded = (part(pk) for pk in group.get("exclude_rule_ids", []))
    return combine(group["operator"], included, excluded)


def combine_queries(operator, included, excluded):
    matches = reduce(and_ if operator == AND else or_, included)
    for query in excluded:
        matches &= ~query
    return matches


def combine_matches(operator, included, excluded):
    return (all if operator == AND else any)(included) and not any(excluded)


def search_filter_or_none(rule):
    search_filter = rule.get_search_filter_for_rule()
    # Elasticsearch matches every resource with an empty bool.
    if search_filter is None or not has_clauses(search_filter):
        return None
    return search_filter


def combine_search_filters(operator, included, excluded):
    included, excluded = list(included), list(excluded)
    # Leaving out a rule Elasticsearch can't express would widen an "and" or an
    # exclusion and narrow an "or", so the whole combination is left out.
    if None in included or None in excluded:
        return None
    search_filter = Bool()
    for excluded_filter in excluded:
        search_filter.must_not(excluded_filter)
    for included_filter in included:
        if operator == AND:
            search_filter.filter(included_filter)
        else:
            search_filter.should(included_filter)
    return search_filter
