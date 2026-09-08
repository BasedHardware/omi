import os

import firebase_admin
from dotenv import load_dotenv

from database._client import get_users_uid

load_dotenv('../../.dev.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '')
firebase_admin.initialize_app()  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped

from typing import Any, Dict, List, cast


import database.conversations as conversations_db

import multiprocessing
import matplotlib.pyplot as plt

# matplotlib ships incomplete stubs; alias as Any to avoid cascading unknown-member warnings.
_plt: Any = cast(Any, plt)

# Assuming get_users_uid() and conversations_db.get_conversations() are already defined


def process_memories(uid: str) -> List[float]:
    durations: List[float] = []
    memories = conversations_db.get_conversations(uid, limit=1000)

    for memory in memories:
        segments = memory.get('transcript_segments', [])
        if not segments:
            continue

        total_duration = (segments[-1]['end'] - segments[0]['start']) / 60
        durations.append(total_duration)

    return durations


def execute() -> None:
    uids = get_users_uid()

    # Use multiprocessing to fetch and process conversations in parallel
    with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
        results = pool.map(process_memories, uids)

    # Flatten the list of durations
    durations = [duration for sublist in results for duration in sublist]

    # Calculate percentage for the y-axis
    total_memories = len(durations)

    # Plot the distribution of durations
    _plt.figure(figsize=(10, 6))

    # Use 'density=False' to show counts, normalize the height manually to percentage
    counts, bins, _ = _plt.hist(durations, bins=50, edgecolor='black')

    # Convert counts to percentages
    percentages = (counts / total_memories) * 100

    # Clear the histogram to plot again with percentage values
    _plt.clf()

    # Plot the histogram with percentages
    _plt.bar(bins[:-1], percentages, width=(bins[1] - bins[0]), edgecolor='black')

    # Add labels and title
    _plt.title('Distribution of Conversation Durations')
    _plt.xlabel('Duration (minutes)')
    _plt.ylabel('Percentage of Total Memories (%)')

    # Show the plot
    _plt.show()


def check():
    memories = conversations_db.get_conversations('', limit=20)
    for memory in memories:
        # print(memory['started_at'])
        started_at = str(memory['started_at']).split(' ')[1].split('.')[0]
        finished_at = str(memory['finished_at']).split(' ')[1].split('.')[0]
        print(started_at, finished_at)


def merge_wrongly_separated_memories() -> None:
    uids = get_users_uid()
    for uid in uids:
        memories = conversations_db.get_conversations(uid, limit=50)
        to_merge: List[Dict[str, Any]] = []
        for memory in memories:
            segments = memory.get('transcript_segments', [])
            if not segments or not memory['finished_at'] or not memory['started_at']:
                continue
            if to_merge:
                last_memory = to_merge[-1]
                if (last_memory['started_at'] - memory['finished_at']).total_seconds() < 120:
                    to_merge.append(memory)
                else:
                    if len(to_merge) > 1:
                        print('merging conversations:')
                        for m in to_merge:
                            print(str(m['started_at']).split('.')[0], str(m['finished_at']).split('.')[0])
                            # merge them
                    to_merge = []
            else:
                to_merge.append(memory)


if __name__ == '__main__':
    merge_wrongly_separated_memories()
