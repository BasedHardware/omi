"""
Tools for answering questions about the Omi/Friend product.
"""

from langchain_core.tools import tool
from utils.app_integrations import get_github_docs_content


@tool
def get_omi_product_info_tool(query: str) -> str:
    """
    Get information about the Omi/Friend product to answer questions about features, functionality, setup, or purchasing.

    Use this tool when the user asks about:
    - How Omi/Friend works
    - What features the app/device has
    - How to set up or use Omi
    - Where to buy the device or pricing information
    - Technical specifications (battery life, connectivity, etc.)
    - App capabilities and functionality
    - Firmware updates or device management
    - Troubleshooting product issues

    DO NOT use this tool for:
    - Questions about the user's personal conversations or memories
    - Questions about what the user said or did
    - Action items or reminders
    - Personal data queries

    Args:
        query: The specific question about Omi/Friend product (e.g., "How does the device connect to my phone?", "What is the battery life?")

    Returns:
        Product documentation content from GitHub that can help answer the question

    Example:
        query="How do I update the firmware on my Omi device?"
        Returns documentation about firmware updates and device management
    """
    # Get GitHub docs content
    context = get_github_docs_content()

    # Format context as a comprehensive documentation string
    context_str = 'Omi/Friend Product Documentation:\n\n'
    for section, content in context.items():
        context_str += f'## {section}\n\n{content}\n\n'

    context_str += (
        '\n\nUse this documentation to answer questions about the Omi/Friend product, its features, setup, and usage.'
    )

    return context_str
