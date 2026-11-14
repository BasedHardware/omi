"""x402 v2 payment execution on Base USDC using the official x402 Python SDK."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from eth_account import Account
from x402 import x402Client
from x402.http import PAYMENT_RESPONSE_HEADER, X_PAYMENT_RESPONSE_HEADER
from x402.http.clients import x402_httpx_transport
from x402.http.utils import decode_payment_response_header
from x402.mechanisms.evm.exact import ExactEvmScheme
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.schemas.errors import NoMatchingRequirementsError

from config import Settings
from payment.ledger import FAILED, NO_PAYMENT, SETTLED, UNKNOWN
from payment.policy import format_usd

logger = logging.getLogger(__name__)

_PAYMENT_HEADERS = ("payment-signature", "x-payment")
_TIMEOUT_SECONDS = 30.0

Resolver = Callable[[str], Awaitable[list[str]]]


@dataclass(frozen=True)
class PaymentResult:
    status: str
    message: str
    tx_hash: str | None = None


class _SignatureTracker(httpx.AsyncBaseTransport):
    """Records whether a signed payment left this server.

    That fact separates a failure that spent nothing from one that may have.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport):
        self.inner = inner
        self.payment_sent = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if any(header in request.headers for header in _PAYMENT_HEADERS):
            self.payment_sent = True
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()


class _PinnedIPTransport(httpx.AsyncBaseTransport):
    """Connects to the address that passed validation, closing the DNS rebinding gap.

    The URL's host becomes the IP, so nothing re-resolves the name. The Host header and
    TLS SNI keep the original name, and the certificate is still verified against it.
    It works on a copy because the x402 transport reuses the caller's request to retry.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport, ip: str):
        self.inner = inner
        self.ip = ip

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=self.ip),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": request.url.raw_host.decode("ascii")},
        )
        return await self.inner.handle_async_request(pinned)

    async def aclose(self) -> None:
        await self.inner.aclose()


async def _system_resolver(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


class PaymentExecutor:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = _system_resolver,
    ):
        self.settings = settings
        self._transport = transport
        self._resolver = resolver

    def _client(self, amount_micro: int) -> x402Client:
        key = self.settings.wallet_private_key
        if key is None:
            raise RuntimeError("wallet not configured")
        signer = EthAccountSigner(Account.from_key(key.get_secret_value()))
        client = x402Client()
        # Only the configured network is registered, so other chains cannot be selected.
        client.register(self.settings.caip_network, ExactEvmScheme(signer=signer))
        # The confirmed amount is the ceiling: a service quoting more is refused.
        client.set_spend_controls({"max_amount_per_payment": format_usd(amount_micro)})
        return client

    async def _resolve_public_ip(self, url: str) -> str | None:
        """Return the IP to pin, or None to block server-side requests into private networks."""
        host = urlsplit(url).hostname or ""
        try:
            addresses = [a.split("%")[0] for a in await self._resolver(host)]
        except OSError:
            return None
        if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
            return None
        return addresses[0]

    async def pay(self, target_url: str, amount_micro: int) -> PaymentResult:
        pinned_ip = await self._resolve_public_ip(target_url)
        if pinned_ip is None:
            return PaymentResult(FAILED, "That service could not be reached, so nothing was paid.")
        try:
            client = self._client(amount_micro)
        except Exception:  # Exception text could echo key material, so it is never logged.
            logger.error("Payment wallet is not usable")
            return PaymentResult(FAILED, "The payment wallet is not set up, so nothing was paid.")

        tracker = _SignatureTracker(_PinnedIPTransport(self._transport or httpx.AsyncHTTPTransport(), pinned_ip))
        try:
            async with httpx.AsyncClient(
                transport=x402_httpx_transport(client, tracker), timeout=_TIMEOUT_SECONDS
            ) as http:
                async with http.stream("GET", target_url) as response:
                    return self._interpret(response, tracker.payment_sent, amount_micro)
        except Exception as exc:
            if tracker.payment_sent:
                logger.warning("Payment outcome unknown: %s", type(exc).__name__)
                return self._unknown()
            if isinstance(exc.__cause__, NoMatchingRequirementsError) or isinstance(exc, NoMatchingRequirementsError):
                return PaymentResult(
                    FAILED,
                    f"The service asked for more than {format_usd(amount_micro)} or a payment "
                    "method this wallet doesn't accept, so nothing was paid.",
                )
            logger.warning("Payment failed before signing: %s", type(exc).__name__)
            return PaymentResult(FAILED, "The payment could not be started, so nothing was paid.")

    @staticmethod
    def _unknown() -> PaymentResult:
        return PaymentResult(
            UNKNOWN,
            "The payment was sent but no confirmation came back. It may have gone through, "
            "so check the wallet before trying again.",
        )

    def _interpret(self, response: httpx.Response, payment_sent: bool, amount_micro: int) -> PaymentResult:
        if not payment_sent:
            if response.is_success:
                return PaymentResult(NO_PAYMENT, "That service didn't ask for payment, so nothing was paid.")
            return PaymentResult(FAILED, f"The service returned HTTP {response.status_code}, so nothing was paid.")

        header = response.headers.get(PAYMENT_RESPONSE_HEADER) or response.headers.get(X_PAYMENT_RESPONSE_HEADER)
        if not response.is_success or not header:
            return self._unknown()
        try:
            settlement = decode_payment_response_header(header)
        except Exception:
            return self._unknown()
        if not settlement.success:
            return PaymentResult(FAILED, "The service rejected the payment, so nothing was paid.")
        return PaymentResult(
            SETTLED,
            f"Paid up to {format_usd(amount_micro)} USDC on {self.settings.network}. "
            f"Transaction: {settlement.transaction}",
            tx_hash=settlement.transaction,
        )
