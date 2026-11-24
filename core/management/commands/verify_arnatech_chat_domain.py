"""Run only from the existing audited ArnaSite production operator boundary."""
import os
import stat

from django.core.management.base import BaseCommand, CommandError

from core.domain_proof_operator import apply_proof, inspect_proof
from core.domain_proof_policy import ProofError
from core.domain_proof_scope import PILOT_HOST


def save_private(path, receipt):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as stream:
        stream.write(receipt)


def read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r", encoding="ascii") as stream:
        metadata = os.fstat(stream.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.geteuid() or metadata.st_nlink != 1 or metadata.st_size > 4096):
            raise ValueError("invalid receipt file")
        return stream.read(4097)


class Command(BaseCommand):
    help = "Verify the fixed Arnatech pilot domain with provider evidence. Dry run unless --apply-receipt."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--write-receipt", metavar="PRIVATE_FILE")
        mode.add_argument("--apply-receipt", metavar="PRIVATE_FILE")

    def handle(self, *args, **options):
        try:
            if options["apply_receipt"]:
                apply_proof(read_private(options["apply_receipt"]))
                self.stdout.write("Verified " + PILOT_HOST + "; audit retained; chat routing remains separately gated.")
            else:
                receipt = inspect_proof()
                if options["write_receipt"]:
                    save_private(options["write_receipt"], receipt)
                self.stdout.write("Dry run: verified provider evidence for " + PILOT_HOST + "; no database change.")
        except ProofError as exc:
            # ProofError contains only locally defined codes; never print raw provider requests or receipts.
            raise CommandError(str(exc)) from None
        except (OSError, ValueError):
            raise CommandError("Unable to use the operator-owned private receipt file.") from None
