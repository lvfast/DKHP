from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import build_settings, load_settings
from app.domain.errors import AppError, ConfigError
from app.logging_config import configure_logging
from app.portal.client import PortalClient
from app.services.notifier import build_notifier
from app.services.rate_limiter import RateLimiter
from app.services.registrar import Registrar
from app.services.scheduler import Scheduler
from app.services.state_store import StateStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="course-registration-service")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--log-format", choices=["human", "json"], default="human")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("run")
    subparsers.add_parser("run-once")
    subparsers.add_parser("dry-run")
    subparsers.add_parser("healthcheck")
    subparsers.add_parser("init-db")
    subparsers.add_parser("reset-db")
    subparsers.add_parser("test-notification")

    args = parser.parse_args(argv)
    configure_logging(args.log_level, log_format=args.log_format)

    try:
        if args.command == "healthcheck":
            return _healthcheck(args.config, args.env_file)
        if args.command == "init-db":
            settings = load_settings(args.config, env_path=args.env_file, require_secrets=False)
            StateStore(settings).init_db()
            print("database initialized")
            return 0
        if args.command == "reset-db":
            settings = load_settings(args.config, env_path=args.env_file, require_secrets=False)
            StateStore(settings).reset_db()
            print("database reset")
            return 0

        settings = load_settings(args.config, env_path=args.env_file, require_secrets=True)
        if args.command == "run":
            return asyncio.run(_run(settings))
        if args.command == "run-once":
            return asyncio.run(_run_once(settings))
        if args.command == "dry-run":
            return asyncio.run(_run_once(settings, dry_run=True))
        if args.command == "test-notification":
            notifier = build_notifier(settings.notification)
            asyncio.run(notifier.send("Course registration service notification test"))
            return 0
    except (AppError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 2


async def _run(settings) -> int:
    registrar = _build_registrar(settings)
    await Scheduler(settings, registrar).run_forever()
    await registrar.portal.close()
    return 0


async def _run_once(settings, *, dry_run: bool | None = None) -> int:
    registrar = _build_registrar(settings)
    all_success = await registrar.run_once(dry_run=dry_run)
    await registrar.portal.close()
    print("all courses successful" if all_success else "run completed")
    return 0


def _build_registrar(settings) -> Registrar:
    store = StateStore(settings)
    portal = PortalClient(settings)
    notifier = build_notifier(settings.notification)
    limiter = RateLimiter(settings.runtime.max_requests_per_minute)
    return Registrar(settings, portal, store, notifier, limiter)


def _healthcheck(config_path: str, env_path: str) -> int:
    try:
        settings = load_settings(config_path, env_path=env_path, require_secrets=False)
    except ConfigError:
        settings = build_settings(
            {
                "portal": {
                    "login_url": "http://localhost/login",
                    "registration_url": "http://localhost/register",
                },
                "courses": [{"id": "healthcheck", "name": "healthcheck"}],
                "database": {"url": "sqlite:///data/app.db"},
            },
            require_secrets=False,
        )
    StateStore(settings).healthcheck()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
