import hmac
import hashlib
import time
from typing import Dict

def verify_omi_signature(
    headers: Dict[str, str], 
    body: bytes, 
    secret: str, 
    tolerance: int = 300
) -> bool:
    """
    Verifica se o webhook recebido foi assinado pela Omi.
    
    :param headers: Dicionário de headers da requisição HTTP.
    :param body: O corpo bruto (raw bytes) da requisição.
    :param secret: O segredo compartilhado (signing_secret).
    :param tolerance: Tolerância de tempo em segundos para evitar replay attacks.
    :return: True se a assinatura for válida, False caso contrário.
    """
    signature_header = headers.get("X-Omi-Signature")
    if not signature_header:
        return False

    try:
        # Parse do header: t=12345678,v1=abcdef...
        parts = dict(item.split('=') for item in signature_header.split(','))
        timestamp_str = parts.get('t')
        received_signature = parts.get('v1')

        if not timestamp_str or not received_signature:
            return False

        # 1. Check Replay Attack (Timestamp)
        timestamp = int(timestamp_str)
        if abs(time.time() - timestamp) > tolerance:
            return False

        # 2. Re-calculate HMAC
        # O payload usado na assinatura foi "timestamp.body"
        signed_payload = f"{timestamp_str}.".encode('utf-8') + body
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            signed_payload,
            hashlib.sha256
        ).hexdigest()

        # 3. Constant-time comparison
        return hmac.compare_digest(expected_signature, received_signature)

    except Exception:
        return False
