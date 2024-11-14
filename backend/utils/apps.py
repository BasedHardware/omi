from typing import List

from database.apps import get_private_apps_db, get_public_unapproved_apps_db, \
    get_public_approved_apps_db, get_app_by_id_db
from database.redis_db import get_enabled_plugins, get_plugin_installs_count, get_plugin_reviews, get_generic_cache, \
    set_generic_cache
from models.app import App
from utils.plugins import weighted_rating


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
            app_dict['reviews'] = []
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
