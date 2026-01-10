import math
import os
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any
import hashlib
import secrets
from database.apps import (
    get_private_apps_db,
    get_public_unapproved_apps_db,
    get_public_approved_apps_db,
    get_app_by_id_db,
    get_app_usage_history_db,
    set_app_review_in_db,
    get_app_usage_count_db,
    get_app_memory_created_integration_usage_count_db,
    get_app_memory_prompt_usage_count_db,
    add_tester_db,
    add_app_access_for_tester_db,
    remove_app_access_for_tester_db,
    remove_tester_db,
    is_tester_db,
    can_tester_access_app_db,
    get_apps_for_tester_db,
    get_app_chat_message_sent_usage_count_db,
    update_app_in_db,
    get_audio_apps_count,
    get_persona_by_uid_db,
    update_persona_in_db,
    get_omi_personas_by_uid_db,
    get_api_key_by_hash_db,
    get_popular_apps_db,
)
from database.auth import get_user_name
from database.conversations import get_conversations
import database.users as users_db
from database.memories import get_memories, get_user_public_memories
from database.redis_db import (
    get_enabled_apps,
    get_app_reviews,
    get_generic_cache,
    set_generic_cache,
    set_app_usage_history_cache,
    get_app_usage_history_cache,
    get_app_money_made_cache,
    set_app_money_made_cache,
    get_apps_installs_count,
    get_apps_reviews,
    get_app_cache_by_id,
    set_app_cache_by_id,
    set_app_review_cache,
    get_app_usage_count_cache,
    set_app_money_made_amount_cache,
    get_app_money_made_amount_cache,
    set_app_usage_count_cache,
    set_user_paid_app,
    get_user_paid_app,
    delete_app_cache_by_id,
    is_username_taken,
    get_user_app_subscription_customer_id,
    set_user_app_subscription_customer_id,
    can_update_persona,
    set_persona_update_timestamp,
)
from database.users import get_stripe_connect_account_id
from models.app import App, UsageHistoryItem, UsageHistoryType
from models.conversation import Conversation
from models.other import Person
from utils import stripe
from utils.llm.persona import condense_conversations, condense_memories, generate_persona_description, condense_tweets
from utils.social import get_twitter_timeline, TwitterProfile, get_twitter_profile

MarketplaceAppReviewUIDs = (
    os.getenv('MARKETPLACE_APP_REVIEWERS').split(',') if os.getenv('MARKETPLACE_APP_REVIEWERS') else []
)


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


def weighted_rating(app):
    C = 3.0  # Assume 3.0 is the mean rating across all apps
    m = 5  # Minimum number of ratings required to be considered
    R = app.rating_avg or 0
    v = app.rating_count or 0
    return (v / (v + m) * R) + (m / (v + m) * C)


def compute_app_score(app: App) -> float:
    """
    Compute app ranking score using the formula:
    score = ((rating_avg / 5) ** 2) * log(1 + rating_count) * sqrt(log(1 + installs))

    - Power of 2 on rating makes ratings below 3.0 fall steeply
    - sqrt on installs reduces dependence on install count

    Rating factor with power of 2:
      5.0 -> 1.0, 4.0 -> 0.64, 3.0 -> 0.36, 2.0 -> 0.16, 1.0 -> 0.04
    """
    rating_avg = app.rating_avg or 0
    rating_count = app.rating_count or 0
    installs = app.installs or 0

    rating_factor = (rating_avg / 5) ** 2  # Steep drop for low ratings
    score = rating_factor * math.log(1 + rating_count) * math.sqrt(math.log(1 + installs))
    return round(score, 4)


def get_popular_apps() -> List[App]:
    popular_apps = []
    if cached_apps := get_generic_cache('get_popular_apps_data'):
        print('get_popular_apps from cache')
        popular_apps = cached_apps
    else:
        print('get_popular_apps from db')
        popular_apps = get_popular_apps_db()
        set_generic_cache('get_popular_apps_data', popular_apps, 60 * 30)  # 30 minutes cached

    app_ids = [app['id'] for app in popular_apps]
    apps_install = get_apps_installs_count(app_ids)
    apps_reviews = get_apps_reviews(app_ids)

    apps = []
    for app in popular_apps:
        app_dict = app
        app_dict['installs'] = apps_install.get(app['id'], 0)
        reviews = apps_reviews.get(app['id'], {})
        sorted_reviews = reviews.values()
        rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if reviews else None
        app_dict['rating_avg'] = rating_avg
        app_dict['rating_count'] = len(sorted_reviews)
        apps.append(App(**app_dict))
    apps = sorted(apps, key=lambda x: x.installs, reverse=True)
    return apps


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
    user_enabled = set(get_enabled_apps(uid))
    all_apps = private_data + public_approved_data + public_unapproved_data + tester_apps
    apps = []

    app_ids = [app['id'] for app in all_apps]
    apps_install = get_apps_installs_count(app_ids)
    apps_review = get_apps_reviews(app_ids) if include_reviews else {}

    for app in all_apps:
        app_dict = app
        app_dict['enabled'] = app['id'] in user_enabled
        app_dict['rejected'] = app['approved'] is False
        app_dict['installs'] = apps_install.get(app['id'], 0)
        if include_reviews:
            reviews = apps_review.get(app['id'], {})
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
    reviews = get_app_reviews(app['id'])
    sorted_reviews = reviews.values()
    rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if reviews else None
    app['reviews'] = [details for details in reviews.values() if details['review']]
    app['rating_avg'] = rating_avg
    app['rating_count'] = len(sorted_reviews)
    app['user_review'] = reviews.get(uid)

    # enabled
    user_enabled = set(get_enabled_apps(uid))
    app['enabled'] = app['id'] in user_enabled

    # install
    apps_install = get_apps_installs_count([app['id']])
    app['installs'] = apps_install.get(app['id'], 0)
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
    apps_installs = get_apps_installs_count(app_ids)
    apps_reviews = get_apps_reviews(app_ids) if include_reviews else {}

    apps = []
    for app in all_apps:
        app_dict = app
        app_dict['installs'] = apps_installs.get(app['id'], 0)
        if include_reviews:
            reviews = apps_reviews.get(app['id'], {})
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
        'type3': type3,
    }

    set_app_money_made_cache(app_id, money)

    return money


def upsert_app_payment_link(
    app_id: str, is_paid_app: bool, price: float, payment_plan: str, uid: str, previous_price: float | None = None
):
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


def set_user_app_sub_customer_id(app_id: str, uid: str, customer_id: str):
    set_user_app_subscription_customer_id(app_id, uid, customer_id)


def find_app_subscription(app_id: str, uid: str, status_filter: str = 'all') -> dict | None:
    """
    Find a user's subscription for a specific app using cached customer ID or metadata search.

    Args:
        app_id: The app ID to search for
        uid: The user ID
        status_filter: Stripe subscription status filter ('all', 'active', etc.)

    Returns:
        Dictionary representation of the subscription or None if not found
    """
    try:

        cached_customer_id = get_user_app_subscription_customer_id(app_id, uid)
        latest_subscription = None

        if cached_customer_id:
            latest_subscription = stripe.find_app_subscription_by_customer_id(
                cached_customer_id, app_id, uid, status_filter
            )

            if latest_subscription is None:
                cached_customer_id = None

        if not latest_subscription and not cached_customer_id:
            latest_subscription = stripe.find_app_subscription_by_metadata(app_id, uid, status_filter)

            # Cache the customer ID for future lookups
            if latest_subscription and latest_subscription.get('customer'):
                set_user_app_subscription_customer_id(app_id, uid, latest_subscription.get('customer'))

        return latest_subscription
    except Exception as e:
        print(f"Error finding app subscription: {e}")
        return None


def is_audio_bytes_app_enabled(uid: str):
    enabled_apps = get_enabled_apps(uid)
    # https://firebase.google.com/docs/firestore/query-data/queries#in_and_array-contains-any
    limit = 30
    enabled_apps = list(set(enabled_apps))
    for i in range(0, len(enabled_apps), limit):
        audio_apps_count = get_audio_apps_count(enabled_apps[i : i + limit])
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
    """Generate a persona prompt based on user memories and conversations."""

    # Get latest memories and user info
    memories = get_memories(uid, limit=250)
    user_name = get_user_name(uid)

    # Get and condense recent conversations
    conversations = get_conversations(uid, limit=10)
    conversation_history = Conversation.conversations_to_string(conversations)
    conversation_history = condense_conversations([conversation_history])

    tweets = None
    if "twitter" in persona['connected_accounts']:
        print("twitter is in connected accounts")
        # Get latest tweets
        timeline = await get_twitter_timeline(persona['twitter']['username'])
        tweets = [{'tweet': tweet.text, 'posted_at': tweet.created_at} for tweet in timeline.timeline]

    # Condense memories
    memories_text = condense_memories([memory['content'] for memory in memories], user_name)

    # Generate updated chat prompt
    persona_prompt = f"""
    You are {user_name} AI. Your objective is to personify {user_name} as accurately as possible for 1:1 cloning.

    You have:
    - **Condensed Facts:** Core identity, personality, values, behavioral patterns, preferences, and continuity for ongoing projects or relationships.
    - **Condensed Context from Recent Conversations:** Key themes, communication nuances, emotional undertones, decision-making patterns, and conversational flow.
    """

    # Add condensed tweets if available
    if tweets:
        persona_prompt += (
            f"- **Condensed Tweets:** Recent tweets from {user_name} for additional context and personality insights.\n"
        )

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
    {memories_text}

    Recent Conversations:
    {conversation_history}

    Recent Tweets:
    {tweets}

    Use these facts, conversations and tweets to shape your personality. Responses should help the conversation go deeper. You have strong opinions, slightly controversial."""
    return persona_prompt


def generate_persona_desc(uid: str, persona_name: str):
    """Generate a persona description based on user memories."""
    memories = get_memories(uid, limit=250)

    persona_description = generate_persona_description(memories, persona_name)
    return persona_description


def update_personas_async(uid: str):
    if not can_update_persona(uid):
        print(f"[PERSONAS] Rate limited - uid={uid} already updated today")
        return

    print(f"[PERSONAS] Starting persona updates in background thread for uid={uid}")
    personas = get_omi_personas_by_uid_db(uid)
    if personas:
        set_persona_update_timestamp(uid)

        threads = []
        for persona in personas:
            threads.append(threading.Thread(target=sync_update_persona_prompt, args=(persona,)))

        [t.start() for t in threads]
        [t.join() for t in threads]
        print(f"[PERSONAS] Finished persona updates in background thread for uid={uid}")
    else:
        print(f"[PERSONAS] No personas found for uid={uid}")


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
    """Update a persona's chat prompt with latest memories and conversations."""
    # Get latest memories and user info
    memories = get_user_public_memories(persona['uid'], limit=250)
    user_name = get_user_name(persona['uid'])

    # Get and condense recent conversations
    conversations = get_conversations(persona['uid'], limit=10)
    conversation_history = Conversation.conversations_to_string(conversations)
    conversation_history = condense_conversations([conversation_history])

    condensed_tweets = None
    # Condense tweets
    if "twitter" in persona['connected_accounts'] and 'twitter' in persona:
        # Get latest tweets
        timeline = await get_twitter_timeline(persona['twitter']['username'])
        tweets = [tweet.text for tweet in timeline.timeline]
        condensed_tweets = condense_tweets(tweets, persona['name'])

    # Condense memories
    memories_text = condense_memories([memory['content'] for memory in memories], user_name)

    # Generate updated chat prompt
    persona_prompt = f"""
You are {user_name} AI. Your objective is to personify {user_name} as accurately as possible for 1:1 cloning.

You have:
- **Condensed Facts:** Core identity, personality, values, behavioral patterns, preferences, and continuity for ongoing projects or relationships.
- **Condensed Context from Recent Conversations:** Key themes, communication nuances, emotional undertones, decision-making patterns, and conversational flow.
"""

    # Add condensed tweets if available
    if condensed_tweets:
        persona_prompt += (
            f"- **Condensed Tweets:** Recent tweets from {user_name} for additional context and personality insights.\n"
        )

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
{memories_text}

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


def app_can_create_memories(app: dict) -> bool:
    """Check if an app can create memories (facts)."""
    return app_has_action(app, 'create_memories') or app_has_action(app, 'create_facts')


def app_can_read_memories(app: dict) -> bool:
    """Check if an app can read memories (facts)."""
    return app_has_action(app, 'read_memories') or app_has_action(app, 'read_facts')


def app_can_read_conversations(app: dict) -> bool:
    """Check if an app can read conversations."""
    return app_has_action(app, 'read_conversations')


def app_can_create_conversation(app: dict) -> bool:
    """Check if an app can create a conversation."""
    return app_has_action(app, 'create_conversation')


def is_user_app_enabled(uid: str, app_id: str) -> bool:
    """Check if a specific app is enabled for the user based on Redis cache."""
    user_enabled_apps = set(get_enabled_apps(uid))
    return app_id in user_enabled_apps


# ********************************
# ********* v2 APPS UTILS ********
# ********************************


def normalize_app_numeric_fields(app_dict: dict) -> dict:
    """Ensure numeric fields that clients expect as float are emitted as float."""

    def _to_float(value):
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return value

    # Normalize fields that should be floats
    for field in ['rating_avg', 'money_made', 'price']:
        if field in app_dict and app_dict[field] is not None:
            app_dict[field] = _to_float(app_dict[field])

    return app_dict


def sort_apps_by_installs_only(apps: List[App]) -> List[App]:
    """Sort apps by install count only (no score calculation)."""
    return sorted(apps, key=lambda a: a.installs, reverse=True)


def sort_apps_by_installs(apps: List[App]) -> List[App]:
    """Sort apps by computed score in descending order.

    Score formula: ((rating_avg / 5) ** 2) * log(1 + rating_count) * sqrt(log(1 + installs))
    This balances review quality, review quantity, and popularity.
    """
    # Compute and assign scores to each app
    for app in apps:
        app.score = compute_app_score(app)

    return sorted(apps, key=lambda a: a.score or 0, reverse=True)


def paginate_apps(apps: List[App], offset: int, limit: int) -> List[App]:
    """Apply pagination to apps list."""
    return apps[offset : offset + limit]


def build_pagination_metadata(total: int, offset: int, limit: int, category: str = None) -> dict:
    """Build pagination metadata for API response."""
    has_next = (offset + limit) < total
    has_previous = offset > 0

    metadata = {
        'total': total,
        'count': min(limit, total - offset),
        'offset': offset,
        'limit': limit,
        'hasNext': has_next,
        'hasPrevious': has_previous,
    }

    # Add navigation links if category is specified
    if category:
        base_url = f"/v2/apps?category={category}"
        metadata['links'] = {
            'next': f"{base_url}&offset={offset + limit}&limit={limit}" if has_next else None,
            'previous': f"{base_url}&offset={max(offset - limit, 0)}&limit={limit}" if has_previous else None,
        }

    return metadata


def get_capabilities_list() -> List[dict]:
    """Get the list of app capabilities for grouping."""
    return [
        {'title': 'Featured', 'id': 'popular'},
        {'title': 'Integrations', 'id': 'external_integration'},
        {'title': 'Chat Assistants', 'id': 'chat'},
        {'title': 'Summary Apps', 'id': 'memories'},
        {'title': 'Realtime Notifications', 'id': 'proactive_notification'},
        {'title': 'Tasks', 'id': 'tasks'},
    ]


def get_categories_list() -> List[dict]:
    """Get the list of app categories for grouping."""
    return [
        {'title': 'Conversation Analysis', 'id': 'conversation-analysis'},
        {'title': 'Personality Clone', 'id': 'personality-emulation'},
        {'title': 'Health', 'id': 'health-and-wellness'},
        {'title': 'Education', 'id': 'education-and-learning'},
        {'title': 'Communication', 'id': 'communication-improvement'},
        {'title': 'Emotional Support', 'id': 'emotional-and-mental-support'},
        {'title': 'Productivity', 'id': 'productivity-and-organization'},
        {'title': 'Entertainment', 'id': 'entertainment-and-fun'},
        {'title': 'Financial', 'id': 'financial'},
        {'title': 'Travel', 'id': 'travel-and-exploration'},
        {'title': 'Safety', 'id': 'safety-and-security'},
        {'title': 'Shopping', 'id': 'shopping-and-commerce'},
        {'title': 'Social', 'id': 'social-and-relationships'},
        {'title': 'News', 'id': 'news-and-information'},
        {'title': 'Utilities', 'id': 'utilities-and-tools'},
        {'title': 'Other', 'id': 'other'},
    ]


def _app_has_auth_steps(app: App) -> bool:
    """Check if app has external_integration with auth_steps."""
    has_external_integration = 'external_integration' in (app.capabilities or set())
    if not has_external_integration:
        return False
    ext_int = app.external_integration
    if ext_int is None:
        return False
    auth_steps = getattr(ext_int, 'auth_steps', None) or []
    return len(auth_steps) > 0


def _is_notification_app(app: App) -> bool:
    """Check if app is a notification/simple integration app.

    Returns True for:
    - Apps with proactive_notification capability
    - Simple integrations (external_integration without auth_steps, chat, or memories)
    """
    app_capabilities = app.capabilities or set()
    if 'proactive_notification' in app_capabilities:
        return True
    has_external_integration = 'external_integration' in app_capabilities
    has_auth_steps = _app_has_auth_steps(app)
    return (
        has_external_integration
        and not has_auth_steps
        and 'chat' not in app_capabilities
        and 'memories' not in app_capabilities
    )


def _get_app_capability(app: App) -> str | None:
    """Determine which capability section an app belongs to.

    Returns the capability id or None if the app doesn't match any section.
    Priority order: external_integration (with auth) > chat > memories > proactive_notification
    """
    app_capabilities = app.capabilities or set()
    has_external_integration = 'external_integration' in app_capabilities
    has_auth_steps = _app_has_auth_steps(app)

    # Notification apps (including simple integrations) go to proactive_notification
    if _is_notification_app(app):
        return 'proactive_notification'

    # External integration with auth_steps
    if has_external_integration and has_auth_steps:
        return 'external_integration'

    # Chat apps (excluding those with external_integration+auth_steps)
    if 'chat' in app_capabilities:
        if not has_external_integration or not has_auth_steps:
            return 'chat'

    # Memories apps (excluding those with chat or external_integration+auth_steps)
    if 'memories' in app_capabilities and 'chat' not in app_capabilities:
        if not has_external_integration or not has_auth_steps:
            return 'memories'

    return None


def group_apps_by_capability(apps: List[App], capabilities: List[dict]) -> Dict[str, List[App]]:
    """Group apps by capability with enhanced filtering rules.

    Groups:
    - popular: Apps marked as is_popular (sorted by installs)
    - proactive_notification: Apps with proactive_notification OR simple integrations
    - external_integration: Apps with external_integration AND auth_steps
    - chat: Apps with chat (excluding those with external_integration+auth_steps)
    - memories: Apps with memories but no chat (excluding those with external_integration+auth_steps)

    Popular apps are excluded from other sections.
    Notification/simple integration apps are excluded from other sections.
    """
    grouped = defaultdict(list)

    # First pass: collect popular apps
    popular_apps = [app for app in apps if getattr(app, 'is_popular', False)]
    popular_app_ids = {app.id for app in popular_apps}
    if popular_apps:
        grouped['popular'] = sort_apps_by_installs_only(popular_apps)

    # Second pass: collect notification apps (exclusive)
    notification_app_ids = set()
    for app in apps:
        if _is_notification_app(app):
            grouped['proactive_notification'].append(app)
            notification_app_ids.add(app.id)

    # Sort notification apps
    if grouped['proactive_notification']:
        grouped['proactive_notification'] = sort_apps_by_installs(grouped['proactive_notification'])

    # Group remaining apps by capability
    for app in apps:
        # Skip popular apps in other sections
        if app.id in popular_app_ids:
            continue

        # Skip notification apps (already processed)
        if app.id in notification_app_ids:
            continue

        capability = _get_app_capability(app)
        if capability and capability != 'proactive_notification':
            grouped[capability].append(app)

    # Sort each capability group by score (except popular which is already sorted by installs)
    for cap_id in grouped:
        if cap_id not in ('popular', 'proactive_notification'):
            grouped[cap_id] = sort_apps_by_installs(grouped[cap_id])

    return grouped


def filter_apps_by_capability(apps: List[App], capability: str) -> List[App]:
    """Filter apps by capability with enhanced filtering rules.

    Note: Unlike group_apps_by_capability (used for main apps page), this does NOT exclude
    popular apps - they should appear on individual capability pages if they match.
    """
    if capability == 'popular':
        return [app for app in apps if getattr(app, 'is_popular', False)]

    filtered_apps = []
    for app in apps:
        # Skip notification apps in non-notification sections
        if capability != 'proactive_notification' and _is_notification_app(app):
            continue

        app_capability = _get_app_capability(app)
        if app_capability == capability:
            filtered_apps.append(app)

    return filtered_apps


def build_capability_groups_response(
    grouped_apps: Dict[str, List[App]], capabilities: List[dict], offset: int, limit: int
) -> List[dict]:
    """Build the groups response for v2/apps endpoint grouped by capability."""
    id_to_title = {c['id']: c['title'] for c in capabilities}

    ordered_keys = [c['id'] for c in capabilities]
    for key in grouped_apps.keys():
        if key not in ordered_keys:
            ordered_keys.append(key)

    groups = []
    for capability_id in ordered_keys:
        apps = grouped_apps.get(capability_id, [])
        if not apps:
            continue

        total = len(apps)
        page = paginate_apps(apps, offset, limit)

        groups.append(
            {
                'capability': {
                    'id': capability_id,
                    'title': id_to_title.get(capability_id, capability_id.title().replace('_', ' ')),
                },
                'data': [normalize_app_numeric_fields(app.model_dump(mode='json')) for app in page],
                'pagination': build_pagination_metadata(total, offset, limit, capability_id),
            }
        )

    return groups


# Base category mapping (used for non-chat capabilities)
_BASE_CATEGORY_MAPPING = {
    # Productivity & Tools
    'personality-emulation': 'productivity-tools',
    'education-and-learning': 'productivity-tools',
    'productivity-and-organization': 'productivity-tools',
    'utilities-and-tools': 'productivity-tools',
    'financial': 'productivity-tools',
    'shopping-and-commerce': 'productivity-tools',
    'news-and-information': 'productivity-tools',
    # Personal & Wellness
    'conversation-analysis': 'personal-wellness',
    'communication-improvement': 'personal-wellness',
    'emotional-and-mental-support': 'personal-wellness',
    'health-and-wellness': 'personal-wellness',
    'safety-and-security': 'personal-wellness',
    'other': 'personal-wellness',
    # Social & Entertainment
    'social-and-relationships': 'social-entertainment',
    'entertainment-and-fun': 'social-entertainment',
    'travel-and-exploration': 'social-entertainment',
}

# Chat-specific overrides (remaps categories to chat-specific master categories)
_CHAT_CATEGORY_OVERRIDES = {
    # Personality Clone (unique to chat)
    'personality-emulation': 'personality-clone',
    # Productivity & Lifestyle (replaces productivity-tools and personal-wellness)
    'education-and-learning': 'productivity-lifestyle',
    'productivity-and-organization': 'productivity-lifestyle',
    'utilities-and-tools': 'productivity-lifestyle',
    'financial': 'productivity-lifestyle',
    'shopping-and-commerce': 'productivity-lifestyle',
    'news-and-information': 'productivity-lifestyle',
    'conversation-analysis': 'productivity-lifestyle',
    'communication-improvement': 'productivity-lifestyle',
    'emotional-and-mental-support': 'productivity-lifestyle',
    'health-and-wellness': 'productivity-lifestyle',
    'safety-and-security': 'productivity-lifestyle',
    'other': 'productivity-lifestyle',
}


def get_master_category_mapping(capability_id: str) -> Dict[str, str]:
    """Get master category mapping for a capability."""
    if capability_id == 'chat':
        return {**_BASE_CATEGORY_MAPPING, **_CHAT_CATEGORY_OVERRIDES}
    return _BASE_CATEGORY_MAPPING


def get_master_categories_list(capability_id: str) -> List[dict]:
    """Get master categories list for a capability."""
    if capability_id == 'chat':
        return [
            {'title': 'Personality Clones', 'id': 'personality-clone'},
            {'title': 'Productivity & Lifestyle', 'id': 'productivity-lifestyle'},
            {'title': 'Social & Entertainment', 'id': 'social-entertainment'},
        ]

    # Default categories for other capabilities
    return [
        {'title': 'Productivity & Tools', 'id': 'productivity-tools'},
        {'title': 'Personal & Lifestyle', 'id': 'personal-wellness'},
        {'title': 'Social & Entertainment', 'id': 'social-entertainment'},
    ]


def group_capability_apps_by_category(apps: List[App], capability_id: str) -> Dict[str, List[App]]:
    """Group apps within a capability by master category."""
    category_mapping = get_master_category_mapping(capability_id)
    default_category = 'productivity-lifestyle' if capability_id == 'chat' else 'personal-wellness'

    grouped = defaultdict(list)
    for app in apps:
        original_category_id = app.category if app.category else 'other'
        master_category_id = category_mapping.get(original_category_id, default_category)
        grouped[master_category_id].append(app)

    # Sort each master category by score
    for master_category_id in grouped:
        grouped[master_category_id] = sort_apps_by_installs(grouped[master_category_id])

    return grouped


def build_capability_category_groups_response(grouped_apps: Dict[str, List[App]], capability_id: str) -> List[dict]:
    """Build response for capability apps grouped by category."""
    master_categories = get_master_categories_list(capability_id)
    id_to_title = {c['id']: c['title'] for c in master_categories}

    ordered_keys = [c['id'] for c in master_categories]
    for key in grouped_apps.keys():
        if key not in ordered_keys:
            ordered_keys.append(key)

    groups = []
    for category_id in ordered_keys:
        apps = grouped_apps.get(category_id, [])
        if not apps:
            continue

        # Capitalize unknown category titles
        title = id_to_title.get(category_id)
        if not title:
            title = ' '.join(word.capitalize() for word in category_id.replace('-', ' ').split())

        groups.append(
            {
                'category': {
                    'id': category_id,
                    'title': title,
                },
                'data': [normalize_app_numeric_fields(app.model_dump(mode='json')) for app in apps],
                'count': len(apps),
            }
        )

    return groups


# ********************************
# *** CHAT TOOLS MANIFEST FETCH **
# ********************************


def fetch_app_chat_tools_from_manifest(manifest_url: str, timeout: int = 10) -> List[Dict[str, Any]] | None:
    """
    Fetch chat tools definitions from an app's manifest endpoint.

    The manifest endpoint should return a JSON object with a 'tools' array containing
    tool definitions with: name, description, endpoint, method, parameters, auth_required, status_message.

    Args:
        manifest_url: Full URL to the manifest endpoint (e.g., https://my-app.com/.well-known/omi-tools.json)
        timeout: Request timeout in seconds

    Returns:
        List of chat tool definitions, or None if fetch fails

    Example manifest response:
    {
        "tools": [
            {
                "name": "add_to_playlist",
                "description": "Add a song to a Spotify playlist",
                "endpoint": "/tools/add_to_playlist",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "song_name": {"type": "string", "description": "Name of the song"},
                        "artist_name": {"type": "string", "description": "Artist name"}
                    },
                    "required": ["song_name"]
                },
                "auth_required": true,
                "status_message": "Adding to playlist..."
            }
        ]
    }
    """
    import requests

    if not manifest_url:
        return None

    try:
        print(f"📥 Fetching chat tools manifest from: {manifest_url}")

        response = requests.get(
            manifest_url, timeout=timeout, headers={'Accept': 'application/json', 'User-Agent': 'Omi-App-Store/1.0'}
        )

        if response.status_code != 200:
            print(f"⚠️ Manifest fetch failed with status {response.status_code}: {manifest_url}")
            return None

        data = response.json()

        # Validate response structure
        if not isinstance(data, dict):
            print(f"⚠️ Invalid manifest format (not a dict): {manifest_url}")
            return None

        tools = data.get('tools', [])

        if not isinstance(tools, list):
            print(f"⚠️ Invalid manifest format ('tools' is not a list): {manifest_url}")
            return None

        # Validate and normalize each tool
        validated_tools = []
        for tool in tools:
            validated_tool = _validate_tool_definition(tool)
            if validated_tool:
                validated_tools.append(validated_tool)
            else:
                print(f"⚠️ Skipping invalid tool in manifest: {tool.get('name', 'unknown')}")

        print(f"✅ Fetched {len(validated_tools)} chat tools from manifest")
        return validated_tools if validated_tools else None

    except requests.Timeout:
        print(f"⚠️ Manifest fetch timed out: {manifest_url}")
        return None
    except requests.RequestException as e:
        print(f"⚠️ Manifest fetch request error: {e}")
        return None
    except ValueError as e:
        print(f"⚠️ Invalid JSON in manifest response: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error fetching manifest: {e}")
        return None


def _validate_tool_definition(tool: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Validate and normalize a single tool definition from the manifest.

    Required fields: name, description, endpoint
    Optional fields: method, parameters, auth_required, status_message

    Returns normalized tool dict or None if invalid.
    """
    if not isinstance(tool, dict):
        return None

    # Check required fields
    name = tool.get('name')
    description = tool.get('description')
    endpoint = tool.get('endpoint')

    if not name or not isinstance(name, str):
        print(f"⚠️ Tool missing required 'name' field")
        return None

    if not description or not isinstance(description, str):
        print(f"⚠️ Tool '{name}' missing required 'description' field")
        return None

    if not endpoint or not isinstance(endpoint, str):
        print(f"⚠️ Tool '{name}' missing required 'endpoint' field")
        return None

    # Build normalized tool definition
    validated = {
        'name': name.strip(),
        'description': description.strip(),
        'endpoint': endpoint.strip(),
        'method': tool.get('method', 'POST').upper(),
        'auth_required': tool.get('auth_required', True),
    }

    # Optional: status_message
    if tool.get('status_message'):
        validated['status_message'] = str(tool['status_message']).strip()

    # Optional: parameters (JSON schema format)
    parameters = tool.get('parameters')
    if parameters and isinstance(parameters, dict):
        # Validate parameters schema structure
        if 'properties' in parameters and isinstance(parameters['properties'], dict):
            validated['parameters'] = {
                'properties': parameters['properties'],
                'required': parameters.get('required', []) if isinstance(parameters.get('required'), list) else [],
            }

    return validated


def app_can_read_tasks(app: dict) -> bool:
    """Check if an app can read tasks."""
    return app_has_action(app, 'read_tasks')
