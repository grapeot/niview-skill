import argparse

from niview_skill import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="niview")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--env-file", default=".env")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("auth", help="authentication commands")
    sub.add_parser("devices", help="list devices")
    sub.add_parser("events", help="list events")
    sub.add_parser("snapshot", help="download the latest snapshot")
    sub.add_parser("poll", help="poll events continuously")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
