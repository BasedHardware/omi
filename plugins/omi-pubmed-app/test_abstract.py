"""Unit tests for efetch abstract extraction (issue #13199)."""

from main import _extract_abstract_from_efetch_xml


def test_extracts_unlabeled_abstract():
    xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <Article>
            <Abstract>
              <AbstractText>This paper studies sleep.</AbstractText>
            </Abstract>
          </Article>
        </MedlineCitation>
      </PubmedArticle>
    </PubmedArticleSet>
    """
    assert _extract_abstract_from_efetch_xml(xml) == "This paper studies sleep."


def test_extracts_labeled_abstract_sections():
    xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <Article>
            <Abstract>
              <AbstractText Label="BACKGROUND">Prior work.</AbstractText>
              <AbstractText Label="METHODS">We measured X.</AbstractText>
            </Abstract>
          </Article>
        </MedlineCitation>
      </PubmedArticle>
    </PubmedArticleSet>
    """
    out = _extract_abstract_from_efetch_xml(xml)
    assert "BACKGROUND: Prior work." in out
    assert "METHODS: We measured X." in out


def test_returns_empty_for_missing_or_bad_xml():
    assert _extract_abstract_from_efetch_xml("<not-closed") == ""
    assert _extract_abstract_from_efetch_xml("<PubmedArticleSet></PubmedArticleSet>") == ""
