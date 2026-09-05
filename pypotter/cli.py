import argparse
import json
import sys

from pypotter.domain.models import KNOWN_SPELLS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pypotter", description="PyPotter spell recognition tools"
    )
    subparsers = parser.add_subparsers(dest="command")
    recognize = subparsers.add_parser("recognize", help="process a known spell")
    recognize.add_argument("spell", choices=KNOWN_SPELLS)
    subparsers.add_parser("web", help="run the local web application")
    subparsers.add_parser("migrate", help="initialize SQLite without deleting legacy files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "recognize":
        from pypotter.config import get_settings
        from pypotter.services.processor import SpellProcessor

        result = SpellProcessor(get_settings().training_dir).process(args.spell)
        print(json.dumps(result.__dict__, default=str))
        return 0
    if args.command == "web":
        import uvicorn

        uvicorn.run("pypotter.api.app:app", host="127.0.0.1", port=8000, reload=False)
        return 0
    if args.command == "migrate":
        from alembic import command
        from alembic.config import Config

        from pypotter.config import get_settings

        settings = get_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        config = Config("alembic.ini")
        config.set_main_option(
            "sqlalchemy.url", settings.resolved_database_url().replace("%", "%%")
        )
        command.upgrade(config, "head")
        print(f"Initialized {settings.resolved_database_url()}")
        return 0
    build_parser().print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
