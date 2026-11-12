from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from arches.app.models.models import GraphModel, Node


def get_resource_node(graphid, nodeid):
    """Return a node of a published resource model, or raise ValidationError."""
    try:
        # Draft graphs (source_identifier set) are replaced when published.
        return Node.objects.get(
            pk=nodeid,
            graph_id=graphid,
            graph__isresource=True,
            graph__source_identifier=None,
        )
    except (Node.DoesNotExist, ValidationError):
        pass
    try:
        is_graph = GraphModel.objects.filter(
            pk=graphid, isresource=True, source_identifier=None
        ).exists()
    except ValidationError:
        is_graph = False
    if not is_graph:
        raise ValidationError(_("%s is not the id of a resource model.") % graphid)
    raise ValidationError(
        _("%(nodeid)s is not the id of a node of graph %(graphid)s.")
        % {"nodeid": nodeid, "graphid": graphid}
    )
