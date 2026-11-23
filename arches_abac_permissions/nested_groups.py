from collections import defaultdict

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from arches_abac_permissions.models import NestedGroup

# Nesting links are ignored and can't be set.
OFF = "off"
# Members of a group get the rules granted to the groups it sits inside.
FROM_PARENTS = "from_parents"
# Members of a group get the rules granted to the groups inside it.
FROM_CHILDREN = "from_children"


def get_inheritance():
    inheritance = getattr(settings, "ABAC_NESTED_GROUP_INHERITANCE", OFF)
    if inheritance not in (OFF, FROM_PARENTS, FROM_CHILDREN):
        raise ImproperlyConfigured(
            "ABAC_NESTED_GROUP_INHERITANCE must be "
            f"{OFF!r}, {FROM_PARENTS!r} or {FROM_CHILDREN!r}."
        )
    return inheritance


def get_parents():
    parents = defaultdict(set)
    for group_id, parent_id in NestedGroup.objects.values_list("group_id", "parent_id"):
        parents[group_id].add(parent_id)
    return parents


def walk(start_ids, links):
    """The groups reached from ``start_ids`` by following ``links``, nearest first."""
    seen = set(start_ids)
    found = set(seen)
    order = []
    while found:
        found = {linked for group_id in found for linked in links[group_id]} - seen
        seen |= found
        order += sorted(found)
    return order


def reachable(start_ids, links):
    """``start_ids`` plus every group reached by following ``links``."""
    start_ids = set(start_ids)
    return start_ids | set(walk(start_ids, links))


def inheritance_links():
    """{group id: ids of the groups whose rules its members directly get}."""
    inheritance = get_inheritance()
    if inheritance == OFF:
        return defaultdict(set)
    parents = get_parents()
    if inheritance == FROM_PARENTS:
        return parents
    children = defaultdict(set)
    for group_id, group_parents in parents.items():
        for parent_id in group_parents:
            children[parent_id].add(group_id)
    return children


def creates_cycle(group_id, parent_ids):
    """Whether putting ``group_id`` inside ``parent_ids`` would loop back to it."""
    return group_id in reachable(parent_ids, get_parents())
