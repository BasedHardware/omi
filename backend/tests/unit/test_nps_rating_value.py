from scripts import nps as nps_script


def test_nps_counts_thumbs_down_as_minus_one_not_cleared_zero():
    ratings = [
        {'uid': 'a', 'value': 1},
        {'uid': 'a', 'value': -1},
        {'uid': 'b', 'value': 0},
        {'uid': 'c', 'value': -1},
    ]
    shown, good, bad = nps_script.summarize_chat_ratings(ratings)
    assert shown == 4
    assert good == 1
    assert bad == 2
