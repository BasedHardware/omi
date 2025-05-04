import click
import logging
import sys
from .server import serve


@click.command()
@click.option("--uid", "-u", type=str, help="User ID")
@click.option("-v", "--verbose", count=True)
def main(uid: str | None, verbose: bool) -> None:
    """MCP Omi Server - Omi functionality for MCP"""
    import asyncio

    logging_level = logging.WARN
    if verbose == 1:
        logging_level = logging.INFO
    elif verbose >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(level=logging_level, stream=sys.stderr)
    print("Server starting...")
    asyncio.run(serve(uid))


if __name__ == "__main__":
    main()
