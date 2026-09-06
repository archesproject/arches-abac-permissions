import re
from django_hosts import patterns, host

host_patterns = patterns(
    "",
    host(re.sub(r"_", r"-", r"arches_abac_permissions"), "arches_abac_permissions.urls", name="arches_abac_permissions"),
)
