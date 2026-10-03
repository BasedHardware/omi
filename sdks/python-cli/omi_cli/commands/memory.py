<content>
"""Memory commands for the OMI CLI."""

import json
import sys
from typing import Any, Dict, List, Optional

import click
from omi_client.authenticated_client import AuthenticatedClient
from omi_client.api.memory_list import memory_list
from omi_client.models import MemoryListResponse, MemoryListResponseItems


@click.group()
def memory():
    """Manage memory items."""
    pass


@memory.command()
@click.option(
    "--category",
    help="Filter by memory category.",
    type=click.Choice(["general", "chat", "code"], case_sensitive=False),
)
@click.option(
    "--output",
    help="Output file path. If not provided, prints to stdout.",
    type=click.Path(writable=True),
    default=None,
)
@click.option(
    "--max-items",
    help="Maximum number of items to fetch. Fetches all items if not set.",
    type=int,
    default=None,
)
def list(category: Optional[str], output: Optional[str], max_items: Optional[int]) -> None:
    """List memory items with pagination support."""
    client = AuthenticatedClient()
    all_items: List[Dict[str, Any]] = []
    page = 1
    limit = 200  # Maximum items per page
    total_fetched = 0
    should_stop = False

    while not should_stop:
        try:
            # Prepare query parameters
            kwargs: Dict[str, Any] = {"limit": limit, "page": page}
            if category:
                kwargs["category"] = category

            # Fetch page
            response = memory_list.sync_detailed(client=client, **kwargs)
            if response.status_code != 200:
                click.echo(f"Error fetching page {page}: {response.status_code}", err=True)
                sys.exit(1)

            data = response.parsed
            if not data or not data.items:
                break  # No more items

            # Convert items to dictionaries and add to our list
            page_items = [item.model_dump() for item in data.items]
            all_items.extend(page_items)
            total_fetched += len(page_items)

            # Check if we've reached max_items
            if max_items and total_fetched >= max_items:
                # Trim to max_items if we exceeded
                all_items = all_items[:max_items]
                should_stop = True
                break

            # Check if we got a full page (less means we're at the end)
            if len(page_items) < limit:
                break

            page += 1

        except Exception as e:
            click.echo(f"Error fetching page {page}: {str(e)}", err=True)
            sys.exit(1)

    # Output the results
    try:
        result = json.dumps(all_items, indent=2)
        if output:
            with open(output, "w") as f:
                f.write(result)
        else:
            click.echo(result)
    except Exception as e:
        click.echo(f"Error writing output: {str(e)}", err=True)
        sys.exit(1)


@memory.command()
@click.option(
    "--category",
    help="Filter by memory category.",
    type=click.Choice(["general", "chat", "code"], case_sensitive=False),
)
@click.option(
    "--output",
    help="Output file path. Required for export.",
    type=click.Path(writable=True),
    required=True,
)
@click.option(
    "--max-items",
    help="Maximum number of items to fetch. Fetches all items if not set.",
    type=int,
    default=None,
)
def export(category: Optional[str], output: str, max_items: Optional[int]) -> None:
    """Export memory items to a JSON file with pagination."""
    client = AuthenticatedClient()
    all_items: List[Dict[str, Any]] = []
    page = 1
    limit = 200  # Maximum items per page
    total_fetched = 0
    should_stop = False

    # Validate output file is writable
    try:
        with open(output, "w") as f:
            pass
    except Exception as e:
        click.echo(f"Error writing to output file: {str(e)}", err=True)
        sys.exit(1)

    while not should_stop:
        try:
            # Prepare query parameters
            kwargs: Dict[str, Any] = {"limit": limit, "page": page}
            if category:
                kwargs["category"] = category

            # Fetch page
            response = memory_list.sync_detailed(client=client, **kwargs)
            if response.status_code != 200:
                click.echo(f"Error fetching page {page}: {response.status_code}", err=True)
                # Don't write partial output
                sys.exit(1)

            data = response.parsed
            if not data or not data.items:
                break  # No more items

            # Convert items to dictionaries and add to our list
            page_items = [item.model_dump() for item in data.items]
            all_items.extend(page_items)
            total_fetched += len(page_items)

            # Check if we've reached max_items
            if max_items and total_fetched >= max_items:
                # Trim to max_items if we exceeded
                all_items = all_items[:max_items]
                should_stop = True
                break

            # Check if we got a full page (less means we're at the end)
            if len(page_items) < limit:
                break

            page += 1

        except Exception as e:
            click.echo(f"Error fetching page {page}: {str(e)}", err=True)
            # Don't write partial output
            sys.exit(1)

    # Write the complete output
    try:
        with open(output, "w") as f:
            json.dump(all_items, f, indent=2)
        click.echo(f"Successfully exported {len(all_items)} items to {output}")
    except Exception as e:
        click.echo(f"Error writing output: {str(e)}", err=True)
        sys.exit(1)
</content>