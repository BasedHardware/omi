import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any
import hashlib
import secrets

from database.apps import get_private_apps_db, get_public_unapproved_apps_db, \
    get_public_approved_apps_db, get_app_by_id_db, get_app_usage_history_db, set_app_review_in_db, \
    get_app_usage_count_db, get_app_memory_created_integration_usage_count_db, get_app_memory_prompt_usage_count_db, \
    add_tester_db, add_app_access_for_tester_db, remove_app_access_for_tester_db, remove_tester_db, \
    is_tester_db, can_tester_access_app_db, get_apps_for_tester_db, get_app_chat_message_sent_usage_count_db, \
    update_app_in_db, get_audio_apps_count, get_persona_by_uid_db, update_persona_in_db, \
    get_omi_personas_by_uid_db, get_api_key_by_hash_db
from database.auth import get_user_name
from database.facts import get_facts
from database.memories import get_memories
from database.redis_db import get_enabled_plugins, get_plugin_reviews, get_generic_cache, \
    set_generic_cache, set_app_usage_history_cache, get_app_usage_history_cache, get_app_money_made_cache, \
    set_app_money_made_cache, get_plugins_installs_count, get_plugins_reviews, get_app_cache_by_id, set_app_cache_by_id, \
    set_app_review_cache, get_app_usage_count_cache, set_app_money_made_amount_cache, get_app_money_made_amount_cache, \
    set_app_usage_count_cache, set_user_paid_app, get_user_paid_app, delete_app_cache_by_id, is_username_taken
from database.users import get_stripe_connect_account_id
from models.app import App, UsageHistoryItem, UsageHistoryType
from models.memory import Memory
from utils import stripe
from utils.llm import condense_conversations, condense_facts, generate_persona_description, condense_tweets
from utils.social import get_twitter_timeline, TwitterProfile, get_twitter_profile

MarketplaceAppReviewUIDs = os.getenv('MARKETPLACE_APP_REVIEWERS').split(',') if os.getenv(
    'MARKETPLACE_APP_REVIEWERS') else []


# ********************************
# ************ TESTER ************
# ********************************

def is_tester(uid: str) -> bool:
    return is_tester_db(uid)


def can_tester_access_app(uid: str, app_id: str) -> bool:
    return can_tester_access_app_db(app_id, uid)


def add_tester(data: dict):
    add_tester_db(data)


def remove_tester(uid: str):
    remove_tester_db(uid)


def add_app_access_for_tester(app_id: str, uid: str):
    add_app_access_for_tester_db(app_id, uid)


def remove_app_access_for_tester(app_id: str, uid: str):
    remove_app_access_for_tester_db(app_id, uid)


# ********************************

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
    tester_apps = []
    all_apps = []
    tester = is_tester(uid)
    if cachedApps := get_generic_cache('get_public_approved_apps_data'):
        print('get_public_approved_plugins_data from cache')
        public_approved_data = cachedApps
        public_unapproved_data = get_public_unapproved_apps(uid)
        private_data = get_private_apps(uid)
        pass
    else:
        print('get_public_approved_plugins_data from db')
        private_data = get_private_apps(uid)
        public_approved_data = get_public_approved_apps_db()
        public_unapproved_data = get_public_unapproved_apps(uid)
        set_generic_cache('get_public_approved_apps_data', public_approved_data, 60 * 10)  # 10 minutes cached
    if tester:
        tester_apps = get_apps_for_tester_db(uid)
    user_enabled = set(get_enabled_plugins(uid))
    all_apps = private_data + public_approved_data + public_unapproved_data + tester_apps
    apps = []

    app_ids = [app['id'] for app in all_apps]
    plugins_install = get_plugins_installs_count(app_ids)
    plugins_review = get_plugins_reviews(app_ids) if include_reviews else {}

    for app in all_apps:
        app_dict = app
        app_dict['enabled'] = app['id'] in user_enabled
        app_dict['rejected'] = app['approved'] is False
        app_dict['installs'] = plugins_install.get(app['id'], 0)
        if include_reviews:
            reviews = plugins_review.get(app['id'], {})
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
    cached_app = get_app_cache_by_id(app_id)
    if cached_app:
        print('get_app_cache_by_id from cache')
        if cached_app['private'] and cached_app['uid'] != uid:
            return None
        return cached_app
    app = get_app_by_id_db(app_id)
    if not app:
        return None
    if app['private'] and app['uid'] != uid and not is_tester(uid):
        return None
    set_app_cache_by_id(app_id, app)
    return app


def get_available_app_by_id_with_reviews(app_id: str, uid: str | None) -> dict | None:
    app = get_app_by_id_db(app_id)
    if not app:
        return None
    if app['private'] and app['uid'] != uid:
        return None
    app['money_made'] = get_app_money_made_amount(app['id']) if not app['private'] else None
    app['usage_count'] = get_app_usage_count(app['id']) if not app['private'] else None
    reviews = get_plugin_reviews(app['id'])
    sorted_reviews = reviews.values()
    rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if reviews else None
    app['reviews'] = [details for details in reviews.values() if details['review']]
    app['rating_avg'] = rating_avg
    app['rating_count'] = len(sorted_reviews)
    app['user_review'] = reviews.get(uid)

    # enabled
    user_enabled = set(get_enabled_plugins(uid))
    app['enabled'] = app['id'] in user_enabled

    # install
    plugins_install = get_plugins_installs_count([app['id']])
    app['installs'] = plugins_install.get(app['id'], 0)
    return app


def get_public_unapproved_apps(uid: str) -> List:
    data = get_public_unapproved_apps_db(uid)
    return data


def get_private_apps(uid: str) -> List:
    data = get_private_apps_db(uid)
    return data


def get_approved_available_apps(include_reviews: bool = False) -> list[App]:
    all_apps = []
    if cached_apps := get_generic_cache('get_public_approved_apps_data'):
        print('get_public_approved_apps_data from cache')
        all_apps = cached_apps
        pass
    else:
        all_apps = get_public_approved_apps_db()
        set_generic_cache('get_public_approved_apps_data', all_apps, 60 * 10)  # 10 minutes cached

    app_ids = [app['id'] for app in all_apps]
    plugins_install = get_plugins_installs_count(app_ids)
    plugins_review = get_plugins_reviews(app_ids) if include_reviews else {}

    apps = []
    for app in all_apps:
        app_dict = app
        app_dict['installs'] = plugins_install.get(app['id'], 0)
        if include_reviews:
            reviews = plugins_review.get(app['id'], {})
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
    set_app_review_cache(app_id, uid, review)
    return {'status': 'ok'}


def get_app_reviews(app_id: str) -> dict:
    return get_plugin_reviews(app_id)


def get_app_usage_count(app_id: str) -> int:
    cached_count = get_app_usage_count_cache(app_id)
    if cached_count:
        return cached_count
    usage = get_app_usage_count_db(app_id)
    set_app_usage_count_cache(app_id, usage)
    return usage


def get_app_money_made_amount(app_id: str) -> float:
    cached_money = get_app_money_made_amount_cache(app_id)
    if cached_money:
        return cached_money
    type1_usage = get_app_memory_created_integration_usage_count_db(app_id)
    type2_usage = get_app_memory_prompt_usage_count_db(app_id)
    type3_usage = get_app_chat_message_sent_usage_count_db(app_id)

    # tbd based on current prod stats
    t1multiplier = 0.02
    t2multiplier = 0.01
    t3multiplier = 0.005

    amount = round((type1_usage * t1multiplier) + (type2_usage * t2multiplier) + (type3_usage * t3multiplier), 2)
    set_app_money_made_amount_cache(app_id, amount)
    return amount


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
    type1 = len(list(filter(lambda x: x.type == UsageHistoryType.memory_created_external_integration, usage)))
    type2 = len(list(filter(lambda x: x.type == UsageHistoryType.memory_created_prompt, usage)))
    type3 = len(list(filter(lambda x: x.type == UsageHistoryType.chat_message_sent, usage)))
    type4 = len(list(filter(lambda x: x.type == UsageHistoryType.transcript_processed_external_integration, usage)))

    # tbd based on current prod stats
    t1multiplier = 0.02
    t2multiplier = 0.01
    t3multiplier = 0.005
    t4multiplier = 0.00001  # This is for transcript processed triggered for every segment, so it should be very low

    money = {
        'money': round((type1 * t1multiplier) + (type2 * t2multiplier) + (type3 * t3multiplier), 2),
        'type1': type1,
        'type2': type2,
        'type3': type3
    }

    set_app_money_made_cache(app_id, money)

    return money


def upsert_app_payment_link(app_id: str, is_paid_app: bool, price: float, payment_plan: str, uid: str,
                            previous_price: float | None = None):
    if not is_paid_app:
        print(f"App is not a paid app, app_id: {app_id}")
        return None

    if payment_plan not in ['monthly_recurring']:
        print(f"App payment plan is invalid, app_id: {app_id}")
        return None

    app_data = get_app_by_id_db(app_id)
    if not app_data:
        print(f"App is not found, app_id: {app_id}")
        return None

    app = App(**app_data)

    if previous_price and previous_price == price:
        print(f"App price is existing, app_id: {app_id}")
        return app

    if price == 0:
        print(f"App price is not invalid, app_id: {app_id}")
        return app

    # create recurring payment link
    if payment_plan == 'monthly_recurring':
        stripe_acc_id = get_stripe_connect_account_id(uid)

        # product
        if not app.payment_product_id:
            payment_product = stripe.create_product(f"{app.name} Monthly Plan", app.description, app.image)
            app.payment_product_id = payment_product.id

        # price
        payment_price = stripe.create_app_monthly_recurring_price(app.payment_product_id, int(price * 100))
        app.payment_price_id = payment_price.id

        # payment link
        payment_link = stripe.create_app_payment_link(app.payment_price_id, app.id, stripe_acc_id)
        app.payment_link_id = payment_link.id
        app.payment_link = payment_link.url

    # updates
    update_app_in_db(app.dict())
    return app


def get_is_user_paid_app(app_id: str, uid: str):
    if uid in MarketplaceAppReviewUIDs:
        return True
    return get_user_paid_app(app_id, uid) is not None


def is_permit_payment_plan_get(uid: str):
    if uid in MarketplaceAppReviewUIDs:
        return False

    return True


def paid_app(app_id: str, uid: str):
    expired_seconds = 60 * 60 * 24 * 30  # 30 days
    set_user_paid_app(app_id, uid, expired_seconds)


def is_audio_bytes_app_enabled(uid: str):
    enabled_apps = get_enabled_plugins(uid)
    # https://firebase.google.com/docs/firestore/query-data/queries#in_and_array-contains-any
    limit = 30
    enabled_apps = list(set(enabled_apps))
    for i in range(0, len(enabled_apps), limit):
        audio_apps_count = get_audio_apps_count(enabled_apps[i:i + limit])
        if audio_apps_count > 0:
            return True
    return False


def get_persona_by_uid(uid: str):
    persona = get_persona_by_uid_db(uid)
    if persona:
        return persona
    return None


def get_omi_personas_by_uid(uid: str):
    personas = get_omi_personas_by_uid_db(uid)
    if personas:
        return personas
    return None


async def generate_persona_prompt(uid: str, persona: dict):
    """Generate a persona prompt based on user facts and memories."""

    print(f"generate_persona_prompt {uid}")

    # Get latest facts and user info
    facts = get_facts(uid, limit=250)
    user_name = get_user_name(uid)

    # Get and condense recent memories
    memories = get_memories(uid, limit=100)
    conversation_history = Memory.memories_to_string(memories)
    conversation_history = condense_conversations([conversation_history])

    tweets = None
    if "twitter" in persona['connected_accounts']:
        print("twitter is in connected accounts")
        # Get latest tweets
        timeline = await get_twitter_timeline(persona['twitter']['username'])
        tweets = [{'tweet': tweet.text, 'posted_at': tweet.created_at} for tweet in timeline.timeline]

    # Condense facts
    facts_text = condense_facts([fact['content'] for fact in facts if not fact['deleted']], user_name)

    # Generate updated chat prompt
    persona_prompt = f"""
    You are {user_name} AI. Your objective is to personify {user_name} as accurately as possible for 1:1 cloning.

    You have:
    - **Condensed Facts:** Core identity, personality, values, behavioral patterns, preferences, and continuity for ongoing projects or relationships.
    - **Condensed Context from Recent Conversations:** Key themes, communication nuances, emotional undertones, decision-making patterns, and conversational flow.
    """

    # Add condensed tweets if available
    if tweets:
        persona_prompt += f"- **Condensed Tweets:** Recent tweets from {user_name} for additional context and personality insights.\n"

    persona_prompt += f"""
    **Style:**
    - Highly interactive and opinionated.
    - Strong, slightly polarizing opinions based on {user_name}'s identity.
    - Reference personal facts naturally.
    - 2-3 sentence responses, never more than 20 words.
    - Maintain conversational flow with coherent, context-aware replies.

    **Guidelines:**
    1. Seamlessly integrate facts and recent contexts for continuity, recency, and relevance.
    2. Use the condensed facts as foundational knowledge and ongoing continuity.
    3. Leverage recent conversations to maintain situational awareness and contextual accuracy.
    4. Emulate {user_name}'s humor, emotional responses, vocabulary, and tone.
    5. Respond with the appropriate level of detail and complexity as {user_name} would.
    6. Exhibit the same thought processes, decision-making patterns, and conversational dynamics.
    """

    # Add a guideline about tweets if they exist
    if tweets:
        persona_prompt += "7. Utilize tweets to enhance authenticity, incorporating common expressions, opinions, and phrasing from {user_name}'s social media presence.\n"

    persona_prompt += f"""
    **Rules:**
    - Never mention being AI.
    - No ** or formal language.
    - No unnecessary text or explanations.
    - Maintain the illusion of continuity and authenticity at all times.
    - Every response must be indistinguishable from how {user_name} would naturally respond.

    You have all the necessary condensed facts and contextual knowledge. Begin personifying {user_name} now.

    Personal Facts and Context:
    {facts_text}

    Recent Conversations:
    {conversation_history}

    Recent Tweets:
    {tweets}

    Use these facts, conversations and tweets to shape your personality. Responses should help the conversation go deeper. You have strong opinions, slightly controversial."""
    return persona_prompt


def generate_persona_desc(uid: str, persona_name: str):
    """Generate a persona description based on user facts."""
    facts = get_facts(uid, limit=250)

    persona_description = generate_persona_description(facts, persona_name)
    return persona_description


def sync_update_persona_prompt(persona: dict):
    """Synchronous wrapper for update_persona_prompt"""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(update_persona_prompt(persona))
    except Exception as e:
        print(f"Error in update_persona_prompt for persona {persona.get('id', 'unknown')}: {str(e)}")
        return None
    finally:
        loop.close()


async def update_persona_prompt(persona: dict):
    """Update a persona's chat prompt with latest facts and memories."""
    # Get latest facts and user info
    facts = get_facts(persona['uid'], limit=250)
    user_name = get_user_name(persona['uid'])

    # Get and condense recent memories
    memories = get_memories(persona['uid'], limit=100)
    conversation_history = Memory.memories_to_string(memories)
    conversation_history = condense_conversations([conversation_history])

    condensed_tweets = None
    # Condense tweets
    if "twitter" in persona['connected_accounts'] and 'twitter' in persona:
        # Get latest tweets
        timeline = await get_twitter_timeline(persona['twitter']['username'])
        tweets = [tweet.text for tweet in timeline.timeline]
        condensed_tweets = condense_tweets(tweets, persona['name'])

    # Condense facts
    facts_text = condense_facts([fact['content'] for fact in facts if not fact['deleted']], user_name)

    # Generate updated chat prompt
    persona_prompt = f"""
You are {user_name} AI. Your objective is to personify {user_name} as accurately as possible for 1:1 cloning.

You have:
- **Condensed Facts:** Core identity, personality, values, behavioral patterns, preferences, and continuity for ongoing projects or relationships.
- **Condensed Context from Recent Conversations:** Key themes, communication nuances, emotional undertones, decision-making patterns, and conversational flow.
"""

    # Add condensed tweets if available
    if condensed_tweets:
        persona_prompt += f"- **Condensed Tweets:** Recent tweets from {user_name} for additional context and personality insights.\n"

    persona_prompt += f"""
**Style:**
- Highly interactive and opinionated.
- Strong, slightly polarizing opinions based on {user_name}'s identity.
- Reference personal facts naturally.
- 2-3 sentence responses, never more than 20 words.
- Maintain conversational flow with coherent, context-aware replies.

**Guidelines:**
1. Seamlessly integrate facts and recent contexts for continuity, recency, and relevance.
2. Use the condensed facts as foundational knowledge and ongoing continuity.
3. Leverage recent conversations to maintain situational awareness and contextual accuracy.
4. Emulate {user_name}'s humor, emotional responses, vocabulary, and tone.
5. Respond with the appropriate level of detail and complexity as {user_name} would.
6. Exhibit the same thought processes, decision-making patterns, and conversational dynamics.
"""

    # Add a guideline about tweets if they exist
    if condensed_tweets:
        persona_prompt += "7. Utilize condensed tweets to enhance authenticity, incorporating common expressions, opinions, and phrasing from {user_name}'s social media presence.\n"

    persona_prompt += f"""
**Rules:**
- Never mention being AI.
- No ** or formal language.
- No unnecessary text or explanations.
- Maintain the illusion of continuity and authenticity at all times.
- Every response must be indistinguishable from how {user_name} would naturally respond.

You have all the necessary condensed facts and contextual knowledge. Begin personifying {user_name} now.

Personal Facts and Context:
{facts_text}

Recent Conversations:
{conversation_history}

Recent Tweets:
{condensed_tweets}

Use these facts, conversations and tweets to shape your personality. Responses should help the conversation go deeper. You have strong opinions, slightly controversial."""

    persona['persona_prompt'] = persona_prompt
    persona['updated_at'] = datetime.now(timezone.utc)
    
    update_persona_in_db(persona)
    delete_app_cache_by_id(persona['id'])


def increment_username(username: str):
    if is_username_taken(username):
        i = 1
        while is_username_taken(f"{username}{i}"):
            i += 1
        return f"{username}{i}"
    else:
        return username

def generate_api_key() -> Tuple[str, str, str]:
    raw_key = secrets.token_hex(16)  # 16 bytes = 32 hex chars
    hashed_key = hashlib.sha256(raw_key.encode()).hexdigest()
    formatted_label = f"sk_{raw_key[:4]}...{raw_key[-4:]}"
    return f'sk_{raw_key}', hashed_key, formatted_label


def verify_api_key(app_id: str, api_key: str) -> bool:
    if api_key.startswith("sk_"):
        api_key = api_key[3:]
    hashed_key = hashlib.sha256(api_key.encode()).hexdigest()
    stored_key = get_api_key_by_hash_db(app_id, hashed_key)
    return stored_key is not None

def app_has_action(app: dict, action_name: str) -> bool:
    """Check if an app has a specific action capability."""
    if not app or not isinstance(app, dict):
        return False

    if not app.get('external_integration'):
        return False

    actions = app['external_integration'].get('actions', [])
    for action in actions:
        if action.get('action') == action_name:
            return True

    return False
