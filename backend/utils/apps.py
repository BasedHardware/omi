from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Dict

from database.apps import get_private_apps_db, get_public_unapproved_apps_db, \
    get_public_approved_apps_db, get_app_by_id_db, get_app_usage_history_db, set_app_review_in_db
from database.redis_db import get_enabled_plugins, get_plugin_installs_count, get_plugin_reviews, get_generic_cache, \
    set_generic_cache, set_app_usage_history_cache, get_app_usage_history_cache, get_app_money_made_cache, \
    set_app_money_made_cache, set_plugin_review
from models.app import App, UsageHistoryItem, UsageHistoryType


def weighted_rating(plugin):
    C = 3.0  # Assume 3.0 is the mean rating across all plugins
    m = 5  # Minimum number of ratings required to be considered
    R = plugin.rating_avg or 0
    v = plugin.rating_count or 0
    return (v / (v + m) * R) + (m / (v + m) * C)


def get_available_apps(uid: str, include_reviews: bool = False) -> List[App]:
    private_data = []
    public_approved_data = []
    public_unapproved_data = []
    all_apps = []
    if cachedApps := get_generic_cache('get_public_approved_apps_data'):
        print('get_public_approved_plugins_data from cache----------------------------')
        public_approved_data = cachedApps
        public_unapproved_data = get_public_unapproved_apps_db(uid)
        private_data = get_private_apps_db(uid)
        pass
    else:
        print('get_public_approved_plugins_data from db----------------------------')
        private_data = get_private_apps_db(uid)
        public_approved_data = get_public_approved_apps_db()
        public_unapproved_data = get_public_unapproved_apps_db(uid)
        set_generic_cache('get_public_approved_apps_data', public_approved_data, 60 * 10)  # 10 minutes cached
    user_enabled = set(get_enabled_plugins(uid))
    all_apps = private_data + public_approved_data + public_unapproved_data
    apps = []
    for app in all_apps:
        app_dict = app
        app_dict['enabled'] = app['id'] in user_enabled
        app_dict['rejected'] = app['approved'] is False
        app_dict['installs'] = get_plugin_installs_count(app['id'])
        if include_reviews:
            reviews = get_plugin_reviews(app['id'])
            sorted_reviews = reviews.values()
            rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if reviews else None
            app_dict['reviews'] = [details for details in reviews.values() if details['review']]
            app_dict['user_review'] = reviews.get(uid)
            app_dict['rating_avg'] = rating_avg
            app_dict['rating_count'] = len(sorted_reviews)
        apps.append(App(**app_dict))
    if include_reviews:
        apps = sorted(apps, key=weighted_rating, reverse=True)
    return apps


def get_available_app_by_id(app_id: str, uid: str | None) -> dict | None:
    app = get_app_by_id_db(app_id)
    if not app:
        return None
    if app['private'] and app['uid'] != uid:
        return None
    return app


def get_available_app_by_id_with_reviews(app_id: str, uid: str | None) -> dict | None:
    app = get_app_by_id_db(app_id)
    if not app:
        return None
    if app['private'] and app['uid'] != uid:
        return None
    reviews = get_plugin_reviews(app['id'])
    sorted_reviews = reviews.values()
    rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if reviews else None
    app['reviews'] = []
    app['rating_avg'] = rating_avg
    app['rating_count'] = len(sorted_reviews)
    return app


def get_approved_available_apps(include_reviews: bool = False) -> list[App]:
    all_apps = []
    if cached_apps := get_generic_cache('get_public_approved_apps_data'):
        print('get_public_approved_apps_data from cache')
        all_apps = cached_apps
        pass
    else:
        all_apps = get_public_approved_apps_db()
        set_generic_cache('get_public_approved_apps_data', all_apps, 60 * 10)  # 10 minutes cached
    apps = []
    for app in all_apps:
        app_dict = app
        app_dict['installs'] = get_plugin_installs_count(app['id'])
        if include_reviews:
            reviews = get_plugin_reviews(app['id'])
            sorted_reviews = reviews.values()
            rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if reviews else None
            app_dict['reviews'] = []
            app_dict['rating_avg'] = rating_avg
            app_dict['rating_count'] = len(sorted_reviews)
        apps.append(App(**app_dict))
    if include_reviews:
        apps = sorted(apps, key=weighted_rating, reverse=True)
    return apps



def set_app_review(app_id: str, uid: str, review: dict):
    set_app_review_in_db(app_id, uid, review)
    set_plugin_review(app_id, uid, review)
    return {'status': 'ok'}


def get_app_reviews(app_id: str) -> dict:
    return get_plugin_reviews(app_id)

  
def get_app_usage_history(app_id: str) -> list:
    cached_usage = get_app_usage_history_cache(app_id)
    if cached_usage:
        return cached_usage
    usage = get_app_usage_history_db(app_id)
    usage = [UsageHistoryItem(**x) for x in usage]
    # return usage by date grouped count
    by_date = defaultdict(int)
    for item in usage:
        date = item.timestamp.date()
        if date > datetime(2024, 11, 1, tzinfo=timezone.utc).date():
            by_date[date] += 1

    data = [{'date': k, 'count': v} for k, v in by_date.items()]
    data = sorted(data, key=lambda x: x['date'])
    set_app_usage_history_cache(app_id, data)
    return data


def get_app_money_made(app_id: str) -> dict[str, int | float]:
    cached_money = get_app_money_made_cache(app_id)
    if cached_money:
        return cached_money
    usage = get_app_usage_history_db(app_id)
    usage = [UsageHistoryItem(**x) for x in usage]
    for item in usage:
        if item.timestamp.date() < datetime(2024, 11, 1, tzinfo=timezone.utc).date():
            usage.remove(item)
    type1 = len(list(filter(lambda x: x.type == UsageHistoryType.memory_created_external_integration, usage)))
    type2 = len(list(filter(lambda x: x.type == UsageHistoryType.memory_created_prompt, usage)))
    type3 = len(list(filter(lambda x: x.type == UsageHistoryType.chat_message_sent, usage)))

    # tbd based on current prod stats
    t1multiplier = 0.02
    t2multiplier = 0.01
    t3multiplier = 0.005

    money = {
        'money': round((type1 * t1multiplier) + (type2 * t2multiplier) + (type3 * t3multiplier), 2),
        'type1': type1,
        'type2': type2,
        'type3': type3
    }

    set_app_money_made_cache(app_id, money)

    return money
