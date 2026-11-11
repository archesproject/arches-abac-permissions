"""
Per-unit-of-work cache of parsed rule definitions.

Active during a Django request, a Celery task, or a
``rule_definition_cache()`` block. Outside these, nothing is cached.
"""

import json
from contextlib import contextmanager
from contextvars import ContextVar

_cache = ContextVar("abac_rule_definition_cache", default=None)


@contextmanager
def rule_definition_cache():
    """Cache parsed rule definitions inside the block; nested use shares the outer cache."""
    if _cache.get() is not None:
        yield
        return
    token = _cache.set({})
    try:
        yield
    finally:
        _cache.reset(token)


def start_cache(**kwargs):
    _cache.set({})


def clear_cache(**kwargs):
    _cache.set(None)


def get_cached(rule, parse):
    """Return ``parse(rule.definition)``, memoized per rule and definition while a cache is active."""
    cache = _cache.get()
    if cache is None:
        return parse(rule.definition)
    key = (
        parse.__qualname__,
        rule.pk,
        json.dumps(rule.definition, sort_keys=True, default=str),
    )
    if key not in cache:
        cache[key] = parse(rule.definition)
    return cache[key]
