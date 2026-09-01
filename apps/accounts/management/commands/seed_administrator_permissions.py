from django.core.management.base import BaseCommand

from apps.accounts.permissions import seed_administrator_permissions


class Command(BaseCommand):
    help = "Create the Administrator group and synchronize approved application permissions."

    def handle(self, *args: object, **options: object) -> None:
        seed_administrator_permissions()
        self.stdout.write(self.style.SUCCESS("Administrator permissions synchronized."))
