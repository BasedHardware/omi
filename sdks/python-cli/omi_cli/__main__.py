"""Allow `python -m omi_cli` as an alternative entry point to the `omi` console script."""

from omi_cli.main import app


def _main() -> None:
    app()


if __name__ == "__main__":
    _main()
