import hashlib
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class Command(BaseCommand):
    help = "Create, verify, rotate, or restore OneCare HMS database backups."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            choices=["backup", "verify", "restore"],
            default="backup",
            help="Operation mode: backup, verify, or restore.",
        )
        parser.add_argument(
            "--output-dir",
            default=str(Path(settings.BASE_DIR) / "backups"),
            help="Directory where backup artifacts are stored.",
        )
        parser.add_argument(
            "--file",
            dest="backup_file",
            default="",
            help="Target backup file path for verify or restore.",
        )
        parser.add_argument(
            "--retention-days",
            type=int,
            default=14,
            help="Delete backups older than N days during backup mode (0 disables).",
        )

    def handle(self, *args, **options):
        mode = options["mode"]
        db = settings.DATABASES.get("default", {})
        engine = db.get("ENGINE", "")
        out_dir = Path(options["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        if mode == "backup":
            artifact = self._create_backup(engine=engine, db=db, out_dir=out_dir)
            checksum = _sha256_file(artifact)
            sha_path = Path(f"{artifact}.sha256")
            sha_path.write_text(f"{checksum}  {artifact.name}\n", encoding="utf-8")
            if options["retention_days"] > 0:
                self._rotate_backups(out_dir=out_dir, retention_days=options["retention_days"])
            self.stdout.write(self.style.SUCCESS(f"Backup created: {artifact} (sha256={checksum})"))

        elif mode == "verify":
            target = Path(options["backup_file"])
            if not target.is_file():
                raise CommandError("Specify a valid --file path to verify.")
            sha_path = Path(f"{target}.sha256")
            if not sha_path.is_file():
                raise CommandError(f"Checksum sidecar missing: {sha_path}")
            expected = sha_path.read_text(encoding="utf-8").strip().split()[0]
            actual = _sha256_file(target)
            if expected != actual:
                raise CommandError(f"Checksum mismatch for {target}: expected {expected}, got {actual}")
            self.stdout.write(self.style.SUCCESS(f"Checksum verified OK: {target}"))

        elif mode == "restore":
            target = Path(options["backup_file"])
            if not target.is_file():
                raise CommandError("Specify a valid --file path to restore.")
            self._restore_backup(engine=engine, db=db, backup_file=target)
            self.stdout.write(self.style.SUCCESS(f"Restore completed from: {target}"))

    def _create_backup(self, *, engine: str, db: dict, out_dir: Path) -> Path:
        stamp = datetime.now(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if "sqlite" in engine:
            src = Path(db["NAME"])
            if not src.is_file():
                raise CommandError(f"SQLite database not found at {src}")
            dest = out_dir / f"onecare_sqlite_{stamp}.sqlite3"
            shutil.copy2(src, dest)
            return dest

        if "postgres" in engine:
            dest = out_dir / f"onecare_pg_{stamp}.sql"
            env = os.environ.copy()
            if db.get("PASSWORD"):
                env["PGPASSWORD"] = str(db["PASSWORD"])
            cmd = [
                "pg_dump",
                "-h", str(db.get("HOST") or "localhost"),
                "-p", str(db.get("PORT") or "5432"),
                "-U", str(db.get("USER") or "postgres"),
                "-F", "p",
                "-f", str(dest),
                str(db["NAME"]),
            ]
            subprocess.run(cmd, env=env, check=True)
            return dest

        if "mysql" in engine:
            dest = out_dir / f"onecare_mysql_{stamp}.sql"
            env = os.environ.copy()
            if db.get("PASSWORD"):
                env["MYSQL_PWD"] = str(db["PASSWORD"])
            cmd = [
                "mysqldump",
                "-h", str(db.get("HOST") or "localhost"),
                "-P", str(db.get("PORT") or "3306"),
                "-u", str(db.get("USER") or "root"),
                str(db["NAME"]),
            ]
            with dest.open("wb") as f:
                subprocess.run(cmd, env=env, stdout=f, check=True)
            return dest

        raise CommandError(f"Unsupported database engine for backup: {engine}")

    def _restore_backup(self, *, engine: str, db: dict, backup_file: Path) -> None:
        if "sqlite" in engine:
            dest = Path(db["NAME"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, dest)
            return

        if "postgres" in engine:
            env = os.environ.copy()
            if db.get("PASSWORD"):
                env["PGPASSWORD"] = str(db["PASSWORD"])
            cmd = [
                "psql",
                "-h", str(db.get("HOST") or "localhost"),
                "-p", str(db.get("PORT") or "5432"),
                "-U", str(db.get("USER") or "postgres"),
                "-d", str(db["NAME"]),
                "-f", str(backup_file),
            ]
            subprocess.run(cmd, env=env, check=True)
            return

        if "mysql" in engine:
            env = os.environ.copy()
            if db.get("PASSWORD"):
                env["MYSQL_PWD"] = str(db["PASSWORD"])
            cmd = [
                "mysql",
                "-h", str(db.get("HOST") or "localhost"),
                "-P", str(db.get("PORT") or "3306"),
                "-u", str(db.get("USER") or "root"),
                str(db["NAME"]),
            ]
            with backup_file.open("rb") as f:
                subprocess.run(cmd, env=env, stdin=f, check=True)
            return

        raise CommandError(f"Unsupported database engine for restore: {engine}")

    def _rotate_backups(self, *, out_dir: Path, retention_days: int) -> None:
        cutoff = datetime.now(dt_timezone.utc) - timedelta(days=retention_days)
        for path in out_dir.iterdir():
            if path.is_file():
                modified = datetime.fromtimestamp(path.stat().st_mtime, tz=dt_timezone.utc)
                if modified < cutoff:
                    path.unlink(missing_ok=True)