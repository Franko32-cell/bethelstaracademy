from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services import set_account_status, unlock_login
from apps.audit.models import AuditLog


class Command(BaseCommand):
    help = "Clear a user's login lockout and optionally reactivate the account."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "--reactivate",
            action="store_true",
            help="Set the account status to active as well as clearing the login lockout.",
        )

    def handle(self, *args, **options):
        username = options["username"]
        try:
            user = get_user_model().objects.get(username=username)
        except get_user_model().DoesNotExist as exc:
            raise CommandError(f"No user found with username '{username}'.") from exc

        unlock_login(
            user,
            module=AuditLog.Module.ACCOUNTS,
            resource_type="User",
            resource_label=user.username,
        )

        if options["reactivate"]:
            set_account_status(
                user,
                "active",
                module=AuditLog.Module.ACCOUNTS,
                resource_type="User",
                resource_label=user.username,
            )

        action = "unlocked and reactivated" if options["reactivate"] else "unlocked"
        self.stdout.write(self.style.SUCCESS(f"Account '{user.username}' {action}."))