from collections import defaultdict
from typing import Any, Dict, List, Sequence, Tuple

from database.users import get_all_ratings


def summarize_chat_ratings(ratings: Sequence[Dict[str, Any]]) -> Tuple[int, int, int]:
    """Count rating *acts*. 1 is thumbs-up, -1 is thumbs-down, 0 is a user clearing a rating."""
    shown = len(ratings)
    good = bad = 0
    for rating in ratings:
        value = rating.get("value")
        if value == 1:
            good += 1
        elif value == -1:
            bad += 1
    return shown, good, bad


def calculate_nps():
    ratings = get_all_ratings(rating_type="chat_message")
    uid_to_ratings: defaultdict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in ratings:
        uid_to_ratings[r["uid"]].append(r)
    shown, good, bad = summarize_chat_ratings(ratings)

    print(f"Shown: {shown}, Good: {good}, Bad: {bad}")
    answered = good + bad
    if shown:
        print(f"Answered: {answered / shown * 100:.2f}%")
    if answered:
        print(f"NPS: {(good - bad) / answered * 100:.2f} * (Do not rely)")

    print("------------------")


if __name__ == "__main__":
    calculate_nps()
