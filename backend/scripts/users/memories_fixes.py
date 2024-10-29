import os

import firebase_admin
from dotenv import load_dotenv

from database._client import get_users_uid

load_dotenv('../../.dev.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
firebase_admin.initialize_app()

# noinspection PyUnresolvedReferences
from typing import List

# noinspection PyUnresolvedReferences
import numpy as np
# noinspection PyUnresolvedReferences
import plotly.graph_objects as go
# noinspection PyUnresolvedReferences
import umap
# noinspection PyUnresolvedReferences
from plotly.subplots import make_subplots

# noinspection PyUnresolvedReferences
from models.memory import Memory
import database.memories as memories_db

import multiprocessing
import matplotlib.pyplot as plt


# Assuming get_users_uid() and memories_db.get_memories() are already defined

def process_memories(uid):
    durations = []
    memories = memories_db.get_memories(uid, limit=1000)

    for memory in memories:
        segments = memory.get('transcript_segments', [])
        if not segments:
            continue

        total_duration = (segments[-1]['end'] - segments[0]['start']) / 60
        durations.append(total_duration)

    return durations


def execute():
    uids = get_users_uid()

    # Use multiprocessing to fetch and process memories in parallel
    with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
        results = pool.map(process_memories, uids)

    # Flatten the list of durations
    durations = [duration for sublist in results for duration in sublist]

    # Calculate percentage for the y-axis
    total_memories = len(durations)

    # Plot the distribution of durations
    plt.figure(figsize=(10, 6))

    # Use 'density=False' to show counts, normalize the height manually to percentage
    counts, bins, patches = plt.hist(durations, bins=50, edgecolor='black')

    # Convert counts to percentages
    percentages = (counts / total_memories) * 100

    # Clear the histogram to plot again with percentage values
    plt.clf()

    # Plot the histogram with percentages
    plt.bar(bins[:-1], percentages, width=(bins[1] - bins[0]), edgecolor='black')

    # Add labels and title
    plt.title('Distribution of Conversation Durations')
    plt.xlabel('Duration (minutes)')
    plt.ylabel('Percentage of Total Memories (%)')

    # Show the plot
    plt.show()


def check():
    memories = memories_db.get_memories('', limit=20)
    for memory in memories:
        # print(memory['started_at'])
        started_at = str(memory['started_at']).split(' ')[1].split('.')[0]
        finished_at = str(memory['finished_at']).split(' ')[1].split('.')[0]
        print(started_at, finished_at)


def merge_wrongly_separated_memories():
    uids = get_users_uid()
    for uid in uids:
        memories = memories_db.get_memories(uid, limit=50)
        to_merge = []
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
                        print('merging memories:')
                        for m in to_merge:
                            print(str(m['started_at']).split('.')[0], str(m['finished_at']).split('.')[0])
                            # merge them
                    to_merge = []
            else:
                to_merge.append(memory)


if __name__ == '__main__':
    merge_wrongly_separated_memories()
