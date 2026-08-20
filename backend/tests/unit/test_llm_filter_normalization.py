from utils.llm.chat import normalize_filter


def test_normalize_filter_limits_each_item_to_two_words():
    assert normalize_filter('  Project Apollo Mission  ') == 'project apollo'
