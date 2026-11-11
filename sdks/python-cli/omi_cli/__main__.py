"""Allow `python -m omi_cli` as an alternative entry point to the `omi` console script."""

from omi_cli.main import main


if __name__ == "__main__":
    main()
