from collections import Counter
from database.redis_db import r

from database.redis_db import get_enabled_plugins


def get_most_popular_plugins():
    all_plugins = {}
    for key in r.scan_iter("users:*:enabled_plugins"):
        uid = key.decode().split(":")[1]
        enabled_plugins = get_enabled_plugins(uid)
        for plugin in enabled_plugins:
            all_plugins[plugin] = all_plugins.get(plugin, 0) + 1

    sorted_plugins = sorted(all_plugins.items(), key=lambda x: x[1], reverse=True)
    return sorted_plugins


def get_most_popular_plugins_fast():
    plugin_counter = Counter()

    # Use pipeline to fetch all enabled plugins in a single Redis operation
    with r.pipeline() as pipe:
        for key in r.scan_iter("users:*:enabled_plugins"):
            pipe.smembers(key)
        all_enabled_plugins = pipe.execute()

    # Count plugins using Counter
    for plugins in all_enabled_plugins:
        plugin_counter.update(plugin.decode() for plugin in plugins)

    # Return sorted list of tuples (plugin, count)
    return plugin_counter.most_common()


def save_plugin_count():
    # Get the most popular plugins
    popular_plugins = get_most_popular_plugins_fast()

    # Use pipeline to set all counts in a single Redis operation
    with r.pipeline() as pipe:
        for plugin_id, count in popular_plugins:
            pipe.set(f"plugins:{plugin_id}:downloads", count)
        pipe.execute()

    print("Plugin download counts saved successfully.")


def view_all_plugin_count():
    # Use pipeline to get all plugin counts in a single Redis operation
    with r.pipeline() as pipe:
        for key in r.scan_iter("plugins:*:downloads"):
            pipe.get(key)
        all_plugin_counts = pipe.execute()

    # Create a list of tuples (plugin_id, count)
    plugin_counts = []
    for key, count in zip(r.scan_iter("plugins:*:downloads"), all_plugin_counts):
        plugin_id = key.decode().split(":")[1]
        plugin_counts.append((plugin_id, int(count)))

    # Sort the list by count in descending order
    sorted_plugin_counts = sorted(plugin_counts, key=lambda x: x[1], reverse=True)

    # Print the results
    print("Plugin Download Counts:")
    for plugin_id, count in sorted_plugin_counts:
        print(f"{plugin_id}: {count}")

    return sorted_plugin_counts


if __name__ == "__main__":
    # print(get_most_popular_plugins_fast())
    view_all_plugin_count()
