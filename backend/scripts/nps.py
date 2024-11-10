import os
from collections import defaultdict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings


llm_mini = ChatOpenAI(model='gpt-4o-mini')
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

load_dotenv('../.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

from database.users import get_all_ratings
from database.auth import get_user_from_uid


def calculate_nps():
    ratings = get_all_ratings()
    uid_to_ratings = defaultdict(list)
    shown = len(ratings)
    good = bad = 0
    for r in ratings:
        uid_to_ratings[r['uid']].append(r)
        if r['value'] == 1:
            good += 1
        elif r['value'] == 0:
            bad += 1

    print(f'Shown: {shown}, Good: {good}, Bad: {bad}')
    print(f'Answered: {(good + bad) / shown * 100:.2f}%')
    print(f'NPS: {(good - bad) / (good + bad) * 100:.2f} * (Do not rely)')

    print('------------------')
    user_to_avg = {}
    for uid, ratings in uid_to_ratings.items():
        cleaned = [r['value'] for r in ratings if r['value'] != -1]
        if not cleaned:
            continue

        print(uid, cleaned)
        print(get_user_from_uid(uid))
        user_to_avg[uid] = sum(cleaned) / len(cleaned)

    print(user_to_avg)

    # First analytics at October 30, 2024 at 11:24:23PM UTC-7
    # memory opened event to viewed
    # memory created to viewed


if __name__ == '__main__':
    calculate_nps()
