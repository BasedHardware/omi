from concurrent.futures import ThreadPoolExecutor
from typing import Dict
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
import matplotlib.pyplot as plt
from tabulate import tabulate

from database._client import get_users_uid
from database.chat import get_messages


def process_user(uid: str) -> Dict:
    messages = get_messages(uid, limit=50)
    # Filter out day_summary messages
    messages = [
        m for m in messages if m["type"] != "day_summary" and m["sender"] != "ai"
    ]

    # Get timestamps for first and last message if any messages exist
    message_dates = [m["created_at"] for m in messages]
    first_message = min(message_dates) if message_dates else None
    last_message = max(message_dates) if message_dates else None

    # Get first message text
    first_message_text = None
    if messages:
        sorted_messages = sorted(messages, key=lambda m: m["created_at"])
        first_message_text = (
            sorted_messages[0]["text"][:100] + "..."
            if len(sorted_messages[0]["text"]) > 100
            else sorted_messages[0]["text"]
        )

    days_active = None
    if first_message and last_message:
        days_active = (last_message - first_message).days + 1

    # Get weekly activity
    weekly_activity = []
    if first_message:
        for week in range(4):
            week_start = first_message + timedelta(weeks=week)
            week_end = week_start + timedelta(weeks=1)
            had_activity = any(
                week_start <= msg["created_at"] < week_end for msg in messages
            )
            weekly_activity.append(had_activity)

    # Get message sequence for retention
    message_sequence = []
    if messages:
        sorted_msgs = sorted(messages, key=lambda m: m["created_at"])
        message_sequence = [m["text"] for m in sorted_msgs]

    return {
        "uid": uid,
        "human_message_count": len(messages),
        "days_active": days_active,
        "first_message": first_message_text,
        "first_message_date": first_message,
        "weekly_activity": weekly_activity,
        "has_recent_activity": last_message.replace(tzinfo=timezone.utc)
        > (datetime.now(timezone.utc).replace(day=1))
        if last_message
        else False,
        "message_sequence": message_sequence,
    }


def print_and_plot_message_distribution(results):
    message_counts = [r["human_message_count"] for r in results]
    count_distribution = Counter(message_counts)

    # Group counts over 100 together
    total_over_100 = sum(
        count for msgs, count in count_distribution.items() if msgs > 100
    )

    # Prepare data for plotting and printing
    x_values = []
    y_values = []

    for msgs in range(0, 101):
        if msgs in count_distribution:
            print(f"{msgs:8d} | {count_distribution[msgs]}")
            x_values.append(msgs)
            y_values.append(count_distribution[msgs])

    if total_over_100 > 0:
        x_values.append(100)  # Use 100 as the x-value for 100+
        y_values.append(total_over_100)

    # Create the plot
    plt.figure(figsize=(15, 8))
    plt.bar(x_values, y_values, color="skyblue", edgecolor="black")
    plt.title("Distribution of Messages per User", fontsize=14, pad=20)
    plt.xlabel("Number of Messages", fontsize=12)
    plt.ylabel("Number of Users", fontsize=12)

    plt.grid(axis="y", linestyle="--", alpha=0.7)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("scripts/users/message_distribution.png")
    plt.close()


def plot_retention_cohorts(results):
    # Filter users with first message
    users_with_activity = [r for r in results if r["first_message_date"]]

    if not users_with_activity:
        print("No users with activity found")
        return

    total_users = len(users_with_activity)
    weekly_retention = []

    # Calculate retention for each week
    for week in range(4):
        active_users = sum(
            1
            for r in users_with_activity
            if len(r["weekly_activity"]) > week and r["weekly_activity"][week]
        )
        retention_rate = (active_users / total_users) * 100
        weekly_retention.append(retention_rate)

    # Create retention plot
    plt.figure(figsize=(10, 6))
    plt.plot(range(1, 5), weekly_retention, marker="o", linewidth=2, markersize=8)
    plt.title("Weekly Retention Cohorts", fontsize=14, pad=20)
    plt.xlabel("Week", fontsize=12)
    plt.ylabel("Retention Rate (%)", fontsize=12)

    # Add percentage labels on points
    for i, rate in enumerate(weekly_retention):
        plt.annotate(
            f"{rate:.1f}%",
            (i + 1, rate),
            textcoords="offset points",
            xytext=(0, 10),
            ha="center",
        )

    plt.grid(True, linestyle="--", alpha=0.7)
    plt.xticks(range(1, 5))
    plt.ylim(0, 100)
    plt.tight_layout()
    plt.savefig("scripts/users/retention_cohorts.png")
    plt.close()


def plot_message_retention(results):
    # Get all message sequences
    sequences = [r["message_sequence"] for r in results if r["message_sequence"]]

    if not sequences:
        print("No message sequences found")
        return

    # Calculate retention for each message number
    max_messages = 10  # Track retention up to 10th message
    message_retention = []
    initial_users = len(sequences)

    for msg_num in range(max_messages):
        users_with_message = sum(1 for seq in sequences if len(seq) > msg_num)
        retention_rate = (users_with_message / initial_users) * 100
        message_retention.append(retention_rate)

    # Create retention plot
    plt.figure(figsize=(10, 6))
    plt.plot(
        range(1, max_messages + 1),
        message_retention,
        marker="o",
        linewidth=2,
        markersize=8,
    )
    plt.title("Message Number Retention", fontsize=14, pad=20)
    plt.xlabel("Message Number", fontsize=12)
    plt.ylabel("Retention Rate (%)", fontsize=12)

    for i, rate in enumerate(message_retention):
        plt.annotate(
            f"{rate:.1f}%",
            (i + 1, rate),
            textcoords="offset points",
            xytext=(0, 10),
            ha="center",
        )

    plt.grid(True, linestyle="--", alpha=0.7)
    plt.xticks(range(1, max_messages + 1))
    plt.ylim(0, 100)
    plt.tight_layout()
    plt.savefig("scripts/users/message_retention.png")
    plt.close()


def execute():
    uids = get_users_uid()
    results = []

    # Process users in parallel using thread pool
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(process_user, uids))

    # Calculate statistics
    users_with_messages = [r for r in results if r["human_message_count"] > 0]
    message_percentage = (len(users_with_messages) / len(results)) * 100

    print(f"\nAnalyzed {len(uids)} users")
    print(
        f"Users who have sent at least one message: {len(users_with_messages)} ({message_percentage:.1f}%)"
    )

    active_users = [r for r in results if r["has_recent_activity"]]
    print(f"Active users this month: {len(active_users)}")

    # Analyze message types
    greetings = ["hi", "hello", "hey", "hola", "bonjour", "ciao", "hallo", "oi", "olá"]
    message_categories = {
        "greetings": 0,
        "long_messages": 0,
        "short_messages": 0,
        "other_messages": [],
    }

    for r in results:
        if r["first_message"]:
            first_word = r["first_message"].lower().split()[0]
            word_count = len(r["first_message"].split())

            if first_word in greetings:
                message_categories["greetings"] += 1
            elif word_count >= 10:
                message_categories["long_messages"] += 1
            elif word_count < 10:
                message_categories["short_messages"] += 1

            # Store messages that don't fit other categories
            if first_word not in greetings:
                message_categories["other_messages"].append(
                    {"message": r["first_message"], "words": word_count}
                )

    print("\nFirst Message Categories:")
    print("-" * 40)
    print(f"Greeting messages: {message_categories['greetings']}")
    print(f"Long messages (10+ words): {message_categories['long_messages']}")
    print(f"Short messages (<10 words): {message_categories['short_messages']}")

    # Print table of other messages
    other_messages_table = [
        [
            i + 1,
            msg["message"][:50] + "..." if len(msg["message"]) > 50 else msg["message"],
            msg["words"],
        ]
        for i, msg in enumerate(message_categories["other_messages"])
    ]
    print("\nOther First Messages:")
    print(
        tabulate(
            other_messages_table,
            headers=["#", "Message", "Word Count"],
            tablefmt="pipe",
        )
    )

    # Print and plot message distribution
    print_and_plot_message_distribution(results)
    print("\nMessage distribution plot has been saved as 'message_distribution.png'")

    # Plot both retention metrics
    plot_retention_cohorts(results)
    print("Retention cohorts plot has been saved as 'retention_cohorts.png'")

    plot_message_retention(results)
    print("Message retention plot has been saved as 'message_retention.png'")


if __name__ == "__main__":
    execute()
