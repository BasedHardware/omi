"""Canonical local backend factory with a trusted checkout fixture injected.

No synthetic auth override: main.py verifies the actual Firebase Auth emulator
JWT. Use mux.py under the canonical MUX lane owner; never start another stack.
"""

import os
from urllib.parse import urlparse


def create_app():
    if os.getenv('OMI_ENV_STAGE') not in ('local', 'offline'):
        raise RuntimeError('local/offline stage required')
    for variable in ('FIRESTORE_EMULATOR_HOST', 'FIREBASE_AUTH_EMULATOR_HOST'):
        if urlparse('//' + os.getenv(variable, '')).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise RuntimeError('loopback Firestore AND Auth emulators required')
    os.environ['OMI_REFERRAL_CAMPAIGN_ENABLED'] = 'true'
    from main import app
    from database import referral_campaign as ledger
    from routers import referrals
    from tests.unit.fixtures.referral_campaign import LocalCheckoutAdapter, POLICY
    from utils import referral_campaign as policy_module

    # Application auth, customer client, deletion fences and all other routes
    # remain the canonical offline backend. Only commerce has a local fixture.
    ledger.current_policy = lambda: POLICY
    policy_module.current_policy = lambda: POLICY
    referrals.current_policy = lambda: POLICY
    referrals.TrustedCheckoutAdapter = LocalCheckoutAdapter
    os.environ['REFERRAL_PUBLIC_BASE_URL'] = 'https://api.omiapi.com'
    return app
