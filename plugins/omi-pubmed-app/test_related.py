"""Unit tests for related-PMID selection (issue #13646)."""

from main import _select_related_pmids


def test_excludes_source_pmid_when_first():
    links = ["19304878", "14630660", "22909249", "20739307", "31278684"]
    assert _select_related_pmids(links, "19304878", 1) == ["14630660"]
    assert _select_related_pmids(links, "19304878", 5) == [
        "14630660",
        "22909249",
        "20739307",
        "31278684",
    ]


def test_excludes_source_pmid_when_not_first():
    links = ["14630660", "19304878", "22909249"]
    assert _select_related_pmids(links, "19304878", 5) == ["14630660", "22909249"]


def test_source_only_response_yields_no_related():
    assert _select_related_pmids(["19304878"], "19304878", 5) == []


def test_no_source_present_is_unaffected():
    links = ["14630660", "22909249", "20739307"]
    assert _select_related_pmids(links, "19304878", 2) == ["14630660", "22909249"]


def test_handles_integer_ids_consistently():
    links = [19304878, 14630660, 22909249]
    assert _select_related_pmids(links, "19304878", 5) == ["14630660", "22909249"]
