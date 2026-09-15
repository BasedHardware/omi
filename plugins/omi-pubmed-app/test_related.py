"""Unit tests for related-article selection (issue #13646)."""

from main import _select_related_pmids


def test_excludes_source_pmid_leading_the_linkset():
    # Real NCBI elink responses for pubmed_pubmed include the source PMID first.
    links = ["19304878", "14630660", "22909249", "20739307"]
    assert _select_related_pmids(links, "19304878", max_results=1) == ["14630660"]


def test_returns_up_to_max_results_other_articles():
    links = ["1", "2", "3", "4", "5"]
    assert _select_related_pmids(links, "1", max_results=3) == ["2", "3", "4"]


def test_source_pmid_absent_from_linkset():
    links = ["2", "3", "4"]
    assert _select_related_pmids(links, "1", max_results=5) == ["2", "3", "4"]


def test_no_related_articles_besides_source():
    links = ["1"]
    assert _select_related_pmids(links, "1", max_results=5) == []
