"""Runs the real x402 SDK and EIP-712 signing against a fake paid service.

Only the network is mocked. The key is generated per run and never funded.
"""

import base64
import json

import httpx
import pytest
from eth_account import Account
from x402.http.utils import encode_payment_required_header, encode_payment_response_header
from x402.schemas import PaymentRequired, PaymentRequirements, SettleResponse

from config import Settings
from payment.executor import PaymentExecutor
from payment.ledger import FAILED, NO_PAYMENT, SETTLED, UNKNOWN

URL = "https://api.example.com/data"
NETWORK = "eip155:84532"
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
PAY_TO = "0x1111111111111111111111111111111111111111"
TX_HASH = "0x" + "ab" * 32


async def public_resolver(_host):
    return ["93.184.216.34"]


def settings():
    return Settings(wallet_private_key=Account.create().key.hex(), _env_file=None)


def payment_required(price_micro, network=NETWORK, asset=BASE_SEPOLIA_USDC):
    requirements = PaymentRequirements(
        scheme="exact",
        network=network,
        asset=asset,
        amount=str(price_micro),
        pay_to=PAY_TO,
        max_timeout_seconds=60,
        extra={"name": "USDC", "version": "2"},
    )
    body = PaymentRequired(x402_version=2, accepts=[requirements])
    return httpx.Response(402, headers={"PAYMENT-REQUIRED": encode_payment_required_header(body)})


def settled_header(success=True):
    settlement = SettleResponse(success=success, transaction=TX_HASH, network=NETWORK, payer=PAY_TO)
    return {"PAYMENT-RESPONSE": encode_payment_response_header(settlement)}


class PaidService:
    def __init__(self, first, paid=None):
        self.first = first
        self.paid = paid
        self.signatures = []

    def __call__(self, request):
        signature = request.headers.get("payment-signature")
        if signature is None:
            return self.first
        self.signatures.append(json.loads(base64.b64decode(signature)))
        if isinstance(self.paid, Exception):
            raise self.paid
        return self.paid


def executor_for(service):
    return PaymentExecutor(settings(), httpx.MockTransport(service), public_resolver)


async def test_settled_payment_returns_transaction():
    service = PaidService(payment_required(1_000_000), httpx.Response(200, headers=settled_header()))
    result = await executor_for(service).pay(URL, 1_000_000)
    assert result.status == SETTLED
    assert result.tx_hash == TX_HASH
    assert service.signatures[0]["payload"]["authorization"]["value"] == "1000000"


async def test_refuses_service_charging_more_than_confirmed():
    service = PaidService(payment_required(1_000_001), httpx.Response(200, headers=settled_header()))
    result = await executor_for(service).pay(URL, 1_000_000)
    assert result.status == FAILED
    assert service.signatures == []


async def test_refuses_other_network():
    service = PaidService(payment_required(1_000_000, network="eip155:8453"), httpx.Response(200))
    result = await executor_for(service).pay(URL, 1_000_000)
    assert result.status == FAILED
    assert service.signatures == []


async def test_refuses_unrecognized_token():
    fake_token = "0x2222222222222222222222222222222222222222"
    service = PaidService(payment_required(1, asset=fake_token), httpx.Response(200))
    result = await executor_for(service).pay(URL, 1_000_000)
    assert result.status == FAILED
    assert service.signatures == []


async def test_free_resource_spends_nothing():
    result = await executor_for(PaidService(httpx.Response(200))).pay(URL, 1_000_000)
    assert result.status == NO_PAYMENT


async def test_network_error_after_signing_is_unknown():
    service = PaidService(payment_required(1_000_000), httpx.ConnectError("lost"))
    result = await executor_for(service).pay(URL, 1_000_000)
    assert result.status == UNKNOWN
    assert len(service.signatures) == 1


async def test_network_error_before_signing_is_failed():
    def down(_request):
        raise httpx.ConnectError("down")

    assert (await executor_for(down).pay(URL, 1_000_000)).status == FAILED


async def test_success_without_receipt_is_unknown():
    service = PaidService(payment_required(1_000_000), httpx.Response(200))
    assert (await executor_for(service).pay(URL, 1_000_000)).status == UNKNOWN


async def test_rejected_settlement_is_failed():
    service = PaidService(payment_required(1_000_000), httpx.Response(200, headers=settled_header(success=False)))
    assert (await executor_for(service).pay(URL, 1_000_000)).status == FAILED


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "192.168.1.1"])
async def test_blocks_private_addresses(address):
    async def resolver(_host):
        return [address]

    service = PaidService(payment_required(1_000_000))
    result = await PaymentExecutor(settings(), httpx.MockTransport(service), resolver).pay(URL, 1_000_000)
    assert result.status == FAILED
    assert service.signatures == []


async def test_missing_wallet_pays_nothing():
    executor = PaymentExecutor(
        Settings(_env_file=None), httpx.MockTransport(PaidService(httpx.Response(200))), public_resolver
    )
    assert (await executor.pay(URL, 1_000_000)).status == FAILED
