import os
from collections import defaultdict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

#llm_mini = ChatOpenAI(model="gpt-4o-mini")
# replaced with LLM powered from Targon: free open source models hosted at fast TPS
llm_mini = ChatOpenAI(
    model="NousResearch/Meta-Llama-3.1-8B-Instruct",
    api_key="sn4_wr157wetp4eqj1ty1iqq9rht0yqk", #we dont care abt exposing api key here as its free inference anyway (doesnt cost or rate limit)
    base_url="https://api.targon.com/v1",
    #temperature=.7,
    #max_tokens=None,
    #timeout=None,
    #max_retries=2,
)
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

from database.users import get_all_ratings
from database.auth import get_user_from_uid


def calculate_nps():
    ratings = get_all_ratings(rating_type="chat_message")
    uid_to_ratings = defaultdict(list)
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
    # user_to_avg = {}
    # for uid, ratings in uid_to_ratings.items():
    #     cleaned = [r["value"] for r in ratings if r["value"] != -1]
    #     if not cleaned:
    #         continue

    #     print(uid, cleaned)
    #     print(get_user_from_uid(uid))
    #     user_to_avg[uid] = sum(cleaned) / len(cleaned)

    # print(user_to_avg)

    # First analytics at October 30, 2024 at 11:24:23PM UTC-7
    # memory opened event to viewed
    # memory created to viewed


if __name__ == "__main__":
    calculate_nps()
