"""Tests for Stripe webhook error handling fixes (#7282).

Root cause: Stripe webhooks crash with 500 when user doc doesn't exist in Firestore.
The update_user_subscription() call uses Firestore .update() which requires the doc
to exist — deleted or never-created users cause google.api_core.exceptions.NotFound.

Fixes verified via source-level analysis (no heavy imports needed):
1. FirestoreNotFound catch at all update_user_subscription call sites (4 total:
   checkout session, customer.subscription.*, schedule completed, schedule canceled)
2. None-guard for _build_subscription_from_stripe_object in schedule handlers
3. try/except for notification stripe.Subscription.retrieve
4. Logging when _build_subscription_from_stripe_object returns None
"""

from pathlib import Path

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"


def _read_source():
    return PAYMENT_SOURCE.read_text()


# ── Fix 1: FirestoreNotFound guard for deleted users ─────────────────────────


def test_imports_firestore_not_found():
    """payment.py must import FirestoreNotFound for the deleted-user guard."""
    source = _read_source()
    assert 'from google.api_core.exceptions import NotFound as FirestoreNotFound' in source


def test_catches_firestore_not_found_at_all_update_sites():
    """All four webhook paths that call update_user_subscription must catch FirestoreNotFound.

    Call sites:
    1. _update_subscription_from_session (checkout.session.completed path)
    2. customer.subscription.* handler (the actual crash site from logs)
    3. subscription_schedule.completed handler
    4. subscription_schedule.canceled handler
    """
    source = _read_source()
    catches = source.count('except FirestoreNotFound:')
    assert catches >= 4, (
        f"Expected at least 4 FirestoreNotFound catches "
        f"(checkout session, subscription update, schedule completion, schedule cancellation), "
        f"found {catches}"
    )


def test_logs_uid_in_firestore_not_found_warning():
    """FirestoreNotFound catches must include 'not found in Firestore' for debugging."""
    source = _read_source()
    # All handlers should log a warning with the user context (4 FirestoreNotFound + 1 checkout existence check)
    assert source.count('not found in Firestore') >= 5


# ── Fix 2: None-guard for _build_subscription_from_stripe_object ─────────────


def test_build_subscription_catches_unknown_price_id():
    """_build_subscription_from_stripe_object catches ValueError and returns None."""
    source = _read_source()
    # Find the function definition
    func_start = source.index('def _build_subscription_from_stripe_object')
    # Find the next function definition to bound our search
    next_func = source.index('\ndef ', func_start + 1)
    func_body = source[func_start:next_func]

    assert 'except ValueError:' in func_body
    assert 'return None' in func_body


def test_schedule_completion_checks_none_subscription():
    """Schedule completion handler must check for None before .dict() call."""
    source = _read_source()
    # The fix adds: if not new_subscription: ... else: update
    assert 'if not new_subscription:' in source
    assert 'unknown price ID' in source


def test_schedule_cancellation_checks_none_subscription():
    """Schedule cancellation handler must check for None before .cancel_at_period_end = True."""
    source = _read_source()
    # Find the cancellation handler section
    cancel_section_start = source.index("schedule_obj.get('status') == 'canceled'")
    cancel_section = source[cancel_section_start : cancel_section_start + 1500]

    # Must have the None guard before setting cancel_at_period_end
    none_check_pos = cancel_section.index('if not new_subscription:')
    cancel_attr_pos = cancel_section.index('cancel_at_period_end = True')
    assert none_check_pos < cancel_attr_pos, "None check must appear before cancel_at_period_end assignment"


# ── Fix 3: Notification retrieve wrapped in try/except ──────────────────────


def test_notification_retrieve_wrapped():
    """The second stripe.Subscription.retrieve for notifications must be in try/except."""
    source = _read_source()
    assert 'Error retrieving subscription for notification' in source


# ── Existing behavior preserved ──────────────────────────────────────────────


def test_customer_subscription_handler_still_guards_none():
    """customer.subscription.* handler already had 'if new_subscription:' guard — verify it's intact."""
    source = _read_source()
    # Find the customer.subscription handler section
    handler_start = source.index("'customer.subscription.updated'")
    handler_section = source[handler_start : handler_start + 1500]

    # Must still have the None guard from _build_subscription_from_stripe_object
    assert 'if new_subscription:' in handler_section


def test_webhook_returns_success():
    """Webhook must always return {"status": "success"} at the end (Stripe expects 2xx)."""
    source = _read_source()
    # Find the stripe_webhook function
    func_start = source.index("async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):")
    # Get to the return at the end of the function
    func_section = source[func_start:]
    # The function should end with return {"status": "success"}
    assert 'return {"status": "success"}' in func_section


# ── Fix 4: Checkout path FirestoreNotFound guard (CODEx-identified gap) ────


def test_checkout_session_path_guarded():
    """_update_subscription_from_session must catch FirestoreNotFound for deleted users.

    This function is called from checkout.session.completed (line 654) and writes
    via set_stripe_customer_id() and update_user_subscription() — both use .update().
    """
    source = _read_source()
    func_start = source.index('def _update_subscription_from_session')
    next_func = source.index('\ndef ', func_start + 1)
    func_body = source[func_start:next_func]

    assert 'except FirestoreNotFound:' in func_body, "_update_subscription_from_session must catch FirestoreNotFound"
    assert 'not found in Firestore' in func_body


def test_customer_subscription_logs_none_subscription():
    """customer.subscription.* handler must log when _build_subscription_from_stripe_object returns None."""
    source = _read_source()
    handler_start = source.index("'customer.subscription.updated'")
    handler_section = source[handler_start : handler_start + 2500]

    # Must log unknown price ID when subscription build fails
    assert (
        'unknown price ID' in handler_section
    ), "customer.subscription.* handler must log when subscription build returns None"


# ── Fix 5: Inactive subscriptions downgrade without needing valid price ID ──


def test_build_subscription_downgrades_inactive_without_price_check():
    """_build_subscription_from_stripe_object must downgrade inactive subs to Basic
    without requiring a known price ID — prevents stale paid access on deletion."""
    source = _read_source()
    func_start = source.index('def _build_subscription_from_stripe_object')
    next_func = source.index('\ndef ', func_start + 1)
    func_body = source[func_start:next_func]

    # The inactive branch must come BEFORE the price ID resolution
    inactive_check_pos = func_body.index("not in ('active', 'trialing')")
    price_resolve_pos = func_body.index('get_plan_type_from_price_id')
    assert inactive_check_pos < price_resolve_pos, (
        "Inactive status check must precede price ID resolution so deleted/canceled "
        "subscriptions downgrade to Basic even with unknown price IDs"
    )


# ── Fix 6: Checkout path user existence check prevents doc resurrection ────


def test_checkout_path_checks_user_exists_before_processing():
    """checkout.session.completed handler must verify user exists before calling
    get_user_valid_subscription (which has create-on-miss behavior)."""
    source = _read_source()
    # Find the regular user subscription branch within checkout handler
    branch_start = source.index("# Regular user subscription")
    branch_section = source[branch_start : branch_start + 1500]

    # Must have user existence check before get_user_valid_subscription
    assert 'get_user_profile' in branch_section, (
        "Checkout handler must check user exists (via get_user_profile) "
        "before get_user_valid_subscription to prevent doc resurrection"
    )
    profile_pos = branch_section.index('get_user_profile')
    valid_sub_pos = branch_section.index('get_user_valid_subscription')
    assert profile_pos < valid_sub_pos, "User existence check must come before get_user_valid_subscription"
