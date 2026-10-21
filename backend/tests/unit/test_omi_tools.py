from unittest.mock import MagicMock, patch
import pytest

from utils.retrieval.tools.omi_tools import get_omi_product_info_tool


def test_empty_or_none_query():
    res_none = get_omi_product_info_tool.invoke({'query': None})
    assert res_none == "Error: Query cannot be empty."

    res_empty = get_omi_product_info_tool.invoke({'query': '   '})
    assert res_empty == "Error: Query cannot be empty."


@patch('utils.retrieval.tools.omi_tools.get_github_docs_content')
def test_fetch_docs_exception_handled(mock_fetch):
    mock_fetch.side_effect = RuntimeError("Network timeout")
    res = get_omi_product_info_tool.invoke({'query': 'How to set up Omi?'})
    assert "Error: the Omi product documentation could not be retrieved right now" in res


@patch('utils.retrieval.tools.omi_tools.get_github_docs_content')
def test_fetch_docs_empty_result(mock_fetch):
    mock_fetch.return_value = {}
    res = get_omi_product_info_tool.invoke({'query': 'How to set up Omi?'})
    assert "No Omi product documentation is available right now" in res


@patch('utils.retrieval.tools.omi_tools.get_github_docs_content')
def test_fetch_docs_dict_success(mock_fetch):
    mock_fetch.return_value = {
        'Setup': 'Connect via Bluetooth to phone.',
        'Battery': 'Lasts up to 18 hours.'
    }
    res = get_omi_product_info_tool.invoke({'query': 'Battery life?'})
    assert "## Setup\n\nConnect via Bluetooth to phone." in res
    assert "## Battery\n\nLasts up to 18 hours." in res
    assert "Omi/Friend Product Documentation:" in res


@patch('utils.retrieval.tools.omi_tools.get_github_docs_content')
def test_fetch_docs_string_success(mock_fetch):
    mock_fetch.return_value = "Single document markdown content."
    res = get_omi_product_info_tool.invoke({'query': 'Overview?'})
    assert "Single document markdown content." in res


@patch('utils.retrieval.tools.omi_tools.get_github_docs_content')
def test_fetch_docs_null_section_values(mock_fetch):
    mock_fetch.return_value = {
        'Features': None,
        'Specs': 'Water resistant.'
    }
    res = get_omi_product_info_tool.invoke({'query': 'Specs?'})
    assert "## Features\n\n\n\n" in res
    assert "## Specs\n\nWater resistant." in res
