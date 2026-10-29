from django.contrib.auth.models import Group, User
from django.db import transaction
from django.utils.translation import gettext as _

from arches.app.utils.response import JSONResponse
from arches_abac_permissions.views import BadRequest, SuperuserAPIView


def serialize_user(user):
    return {
        "id": user.pk,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "date_joined": user.date_joined.isoformat(),
        "groups": sorted(group.pk for group in user.groups.all()),
    }


def parse_id_list(body, key):
    value = body.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in value
    ):
        raise BadRequest(_("“%(key)s” must be a list of ids.") % {"key": key})
    return set(value)


class UsersView(SuperuserAPIView):
    def get(self, request):
        users = User.objects.prefetch_related("groups").order_by("username")
        return JSONResponse({"users": [serialize_user(user) for user in users]})


class UserGroupMembershipView(SuperuserAPIView):
    """Add and remove groups for one or more users in one transaction."""

    def post(self, request):
        body = self.get_json_body(request)
        user_ids = parse_id_list(body, "user_ids")
        add = parse_id_list(body, "add")
        remove = parse_id_list(body, "remove")
        if not user_ids:
            raise BadRequest(_("Select at least one account."))
        if add & remove:
            raise BadRequest(_("A group cannot be both added and removed."))

        users = list(User.objects.filter(pk__in=user_ids))
        if len(users) != len(user_ids):
            raise BadRequest(_("Unknown account."))
        groups = {
            group.pk: group for group in Group.objects.filter(pk__in=add | remove)
        }
        if set(groups) != add | remove:
            raise BadRequest(_("Unknown group."))

        with transaction.atomic():
            for user in users:
                user.groups.add(*[groups[pk] for pk in add])
                user.groups.remove(*[groups[pk] for pk in remove])

        refreshed = User.objects.filter(pk__in=user_ids).prefetch_related("groups")
        return JSONResponse({"users": [serialize_user(user) for user in refreshed]})
