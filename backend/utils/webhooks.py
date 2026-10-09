import hmac
import hashlib
import time
import json
import httpx
import logging
from typing import Any, Dict
from backend.models.webhook_destination import WebhookDestination

logger = logging.getLogger(__name__)

async def _post_dev_webhook(
    destination: WebhookDestination, 
    payload: Dict[str, Any], 
    idempotency_key: str,
    event_type: str
):
    """
    Envia um webhook para o desenvolvedor com assinatura HMAC para segurança.
    """
    url = destination.url
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
        "X-Omi-Event": event_type,
        "X-Omi-Delivery": idempotency_key
    }

    # Se houver um segredo configurado, assina o payload
    if destination.signing_secret:
        timestamp = str(int(time.time()))
        # O formato da assinatura segue o padrão Stripe: t=<timestamp>,v1=<hmac>
        # O payload para o HMAC é "timestamp.body"
        body_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        signed_payload = f"{timestamp}.".encode('utf-8') + body_bytes
        
        signature = hmac.new(
            destination.signing_secret.encode('utf-8'),
            signed_payload,
            hashlib.sha256
        ).hexdigest()
        
        headers["X-Omi-Signature"] = f"t={timestamp},v1={signature}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=10.0
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Webhook delivery failed for {url}: {e.response.status_code}")
            # Lógica de retry/DLQ existente...
            raise
        except Exception as e:
            logger.error(f"Unexpected error delivering webhook to {url}: {str(e)}")
            raise
