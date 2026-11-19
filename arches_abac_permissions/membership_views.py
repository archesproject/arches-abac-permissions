import logging
import re
from http import HTTPStatus

import phonenumbers
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext as _

from arches.app.models.models import GraphXPublishedGraph, LoadEvent, UserProfile
from arches.app.utils.message_contexts import return_message_context
from arches.app.utils.response import JSONErrorResponse, JSONResponse
from arches_abac_permissions.rule_types import ANONYMOUS_USERNAME
from arches_abac_permissions.views import BadRequest, SuperuserAPIView

logger = logging.getLogger(__name__)

USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,30}$")
SECONDS_PER_HOUR = 3600
USER_FIELDS = ("first_name", "last_name", "email", "username", "phone")


class InviteEmailError(Exception):
    pass


def invite_expiry_hours():
    return settings.PASSWORD_RESET_TIMEOUT // SECONDS_PER_HOUR


def serialize_user(user):
    return {
        "id": user.pk,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        # Logged-out visitors act as this user.
        "is_public": user.username == ANONYMOUS_USERNAME,
        "groups": sorted(group.pk for group in user.groups.all()),
    }


def delete_block(user, requester):
    """Returns (code, message) when the user can't be deleted, else (None, None)."""
    if user.pk == requester.pk:
        return "self", _("You can't delete your own account.")
    if user.username == ANONYMOUS_USERNAME:
        return "public", _("The public user can't be deleted.")
    if user.is_superuser:
        return "superuser", _("Superuser accounts can't be deleted.")
    if (
        GraphXPublishedGraph.objects.filter(user=user).exists()
        or LoadEvent.objects.filter(user=user).exists()
    ):
        return "history", _(
            "This account has published graphs or bulk-load history, so it can't be deleted. Deactivate it instead."
        )
    return None, None


def serialize_user_details(user, requester):
    block_code, block_message = delete_block(user, requester)
    profile = UserProfile.objects.filter(user=user).first()
    return {
        **serialize_user(user),
        "email": user.email,
        "phone": profile.phone if profile else "",
        "can_delete": block_code is None,
        "delete_block_code": block_code,
        "delete_block_reason": block_message,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "date_joined": user.date_joined.isoformat(),
    }


def parse_id_list(body, key):
    value = body.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in value
    ):
        raise BadRequest(_("“%(key)s” must be a list of ids.") % {"key": key})
    return set(value)


def clean_phone(raw):
    """Returns (E.164 number, error) for an optional mobile number."""
    if not raw:
        return "", None
    try:
        number = phonenumbers.parse(raw, None)
    except phonenumbers.NumberParseException:
        number = None
    if number is None or not phonenumbers.is_valid_number(number):
        return raw, _("Enter a valid phone number.")
    if phonenumbers.number_type(number) == phonenumbers.PhoneNumberType.FIXED_LINE:
        return raw, _("Enter a mobile number, not a landline.")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164), None


def validate_user(body, user=None):
    """Returns (cleaned values, {field: message}); `user` is excluded from uniqueness."""
    values = {field: str(body.get(field) or "").strip() for field in USER_FIELDS}
    # Unchanged legacy usernames/phones are kept verbatim and not re-validated.
    keep_username = bool(user) and values["username"] == user.username
    if not keep_username:
        values["username"] = values["username"].lower()
    stored_phone = getattr(getattr(user, "userprofile", None), "phone", "") or ""
    keep_phone = bool(user) and values["phone"] == stored_phone
    errors = {
        field: _("This field is required.")
        for field in ("first_name", "last_name")
        if not values[field]
    }
    others = User.objects.exclude(pk=user.pk) if user else User.objects.all()

    try:
        validate_email(values["email"])
    except ValidationError:
        errors["email"] = _("Enter a valid email address.")
    else:
        if others.filter(email__iexact=values["email"]).exists():
            errors["email"] = _("Another account uses this email.")

    if keep_username:
        pass
    elif not USERNAME_PATTERN.match(values["username"]):
        errors["username"] = _("3–30 characters: letters, numbers, . _ -")
    elif others.filter(username__iexact=values["username"]).exists():
        errors["username"] = _("That username is already in use.")

    if not keep_phone:
        values["phone"], phone_error = clean_phone(values["phone"])
        if phone_error:
            errors["phone"] = phone_error

    for field in ("first_name", "last_name", "email"):
        max_length = User._meta.get_field(field).max_length
        if len(values[field]) > max_length:
            errors[field] = _("Ensure this value has at most %(max)d characters.") % {
                "max": max_length
            }
    return values, errors


def send_account_email(request, user, reset=False):
    """Emails a set-password link: an invitation, or a reset for an existing account."""
    link = request.build_absolute_uri(
        reverse(
            "password_reset_confirm",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": default_token_generator.make_token(user),
            },
        )
    )
    greeting = (
        _(
            "A password reset was requested for your %(app)s account. Use the link "
            "below to choose a new password. The link expires in %(hours)s hours."
        )
        if reset
        else _(
            "An account has been created for you on %(app)s. Use the link below "
            "to choose your password. The link expires in %(hours)s hours."
        )
    )
    context = return_message_context(
        greeting=greeting % {"app": settings.APP_NAME, "hours": invite_expiry_hours()},
        additional_context={
            "button_text": _("Set your password"),
            "link": link,
            "username": user.first_name,
        },
    )
    html_content = render_to_string("email/general_notification.htm", context)
    subject = (
        _("Reset your %(app)s password") if reset else _("Welcome to %(app)s!")
    ) % {"app": settings.APP_NAME}
    message = EmailMultiAlternatives(
        subject,
        render_to_string("email/account_invitation.txt", context),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )
    message.attach_alternative(html_content, "text/html")
    try:
        message.send(fail_silently=False)
    except Exception as error:
        logger.exception("Could not send account email")
        raise InviteEmailError from error


def field_errors(errors):
    return JSONErrorResponse(
        message=_("Correct the highlighted fields."),
        content={"errors": errors},
        status=HTTPStatus.BAD_REQUEST,
    )


def email_failed():
    return JSONErrorResponse(
        message=_("The email could not be sent, so no changes were made."),
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
    )


class UsersView(SuperuserAPIView):
    def get(self, request):
        users = User.objects.prefetch_related("groups").order_by("username")
        return JSONResponse(
            {
                "users": [serialize_user(user) for user in users],
                "invite_expiry_hours": invite_expiry_hours(),
                "current_user_id": request.user.pk,
            }
        )

    def post(self, request):
        values, errors = validate_user(self.get_json_body(request))
        if errors:
            return field_errors(errors)
        try:
            with transaction.atomic():
                user = User(
                    username=values["username"],
                    email=values["email"],
                    first_name=values["first_name"],
                    last_name=values["last_name"],
                )
                user.set_unusable_password()
                user.save()
                UserProfile.objects.update_or_create(
                    user=user, defaults={"phone": values["phone"]}
                )
                send_account_email(request, user)
        except IntegrityError:
            return field_errors({"username": _("That username is already in use.")})
        except InviteEmailError:
            return email_failed()
        return JSONResponse(serialize_user(user), status=HTTPStatus.CREATED)


class UserView(SuperuserAPIView):
    @staticmethod
    def find(user_id):
        return User.objects.prefetch_related("groups").filter(pk=user_id).first()

    @staticmethod
    def not_found():
        return JSONErrorResponse(
            message=_("User not found."), status=HTTPStatus.NOT_FOUND
        )

    def get(self, request, user_id):
        user = self.find(user_id)
        if user is None:
            return self.not_found()
        return JSONResponse(serialize_user_details(user, request.user))

    def patch(self, request, user_id):
        user = self.find(user_id)
        if user is None:
            return self.not_found()
        body = self.get_json_body(request)
        profile = UserProfile.objects.filter(user=user).first()
        current = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "username": user.username,
            "phone": profile.phone if profile else "",
        }
        if user.username == ANONYMOUS_USERNAME and (
            any(field in body for field in USER_FIELDS)
            or body.get("password_action") == "reset"
        ):
            raise BadRequest(_("The public user's account can't be edited."))
        # Status-only or reset-only requests don't re-validate untouched fields.
        if any(field in body for field in USER_FIELDS):
            values, errors = validate_user({**current, **body}, user)
        else:
            values, errors = current, {}
            if body.get("password_action") == "reset" and not user.email:
                errors["email"] = _("Enter a valid email address.")
        is_active = body.get("is_active", user.is_active)
        if not isinstance(is_active, bool):
            raise BadRequest(_("“is_active” must be true or false."))
        if not is_active and user.is_active:
            if user.pk == request.user.pk:
                raise BadRequest(_("You can't deactivate your own account."))
            if user.username == ANONYMOUS_USERNAME:
                raise BadRequest(_("The public user can't be deactivated."))
        if body.get("password_action", "keep") not in ("keep", "reset"):
            raise BadRequest(_("Unknown password action."))
        if errors:
            return field_errors(errors)
        try:
            with transaction.atomic():
                for field in ("first_name", "last_name", "email", "username"):
                    setattr(user, field, values[field])
                user.is_active = is_active
                user.save()
                UserProfile.objects.update_or_create(
                    user=user, defaults={"phone": values["phone"]}
                )
                if body.get("password_action") == "reset":
                    send_account_email(request, user, reset=True)
        except IntegrityError:
            return field_errors({"username": _("That username is already in use.")})
        except InviteEmailError:
            return email_failed()
        return JSONResponse(serialize_user_details(user, request.user))

    def delete(self, request, user_id):
        user = self.find(user_id)
        if user is None:
            return self.not_found()
        code, message = delete_block(user, request.user)
        if code:
            return JSONErrorResponse(
                message=message,
                content={"code": code},
                status=(
                    HTTPStatus.CONFLICT if code == "history" else HTTPStatus.BAD_REQUEST
                ),
            )
        user.delete()
        return HttpResponse(status=HTTPStatus.NO_CONTENT)


class UserGroupMembershipView(SuperuserAPIView):
    """Add and remove groups for one or more users in one transaction."""

    def post(self, request):
        body = self.get_json_body(request)
        user_ids = parse_id_list(body, "user_ids")
        add = parse_id_list(body, "add")
        remove = parse_id_list(body, "remove")
        if not user_ids:
            raise BadRequest(_("Select at least one user."))
        if add & remove:
            raise BadRequest(_("A group cannot be both added and removed."))

        users = list(User.objects.filter(pk__in=user_ids))
        if len(users) != len(user_ids):
            raise BadRequest(_("Unknown user."))
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
