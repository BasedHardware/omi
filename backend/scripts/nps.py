from collections import defaultdict
from typing import Any, Dict, List

from database.users import get_all_ratings


def calculate_nps():
    ratings = get_all_ratings(rating_type="chat_message")
    uid_to_ratings: defaultdict[str, List[Dict[str, Any]]] = defaultdict(list)
    shown = len(ratings)
    good = bad = 0
    for r in ratings:
        uid_to_ratings[r["uid"]].append(r)
        if r["value"] == 1:
            good += 1
        elif r["value"] == 0:
            bad += 1

    print(f"Shown: {shown}, Good: {good}, Bad: {bad}")
    print(f"Answered: {(good + bad) / shown * 100:.2f}%")
    print(f"NPS: {(good - bad) / (good + bad) * 100:.2f} * (Do not rely)")

    print("------------------")


if __name__ == "__main__":
    calculate_nps()
