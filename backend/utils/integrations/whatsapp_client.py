"""
WhatsApp Cloud API integration for AI Clone.

Uses Meta's official WhatsApp Cloud API (bot approach) — the Omi bot phone number
receives messages from the user's contacts and replies on the user's behalf.

Setup (per user):
  1. Create a WhatsApp Business Account at https://developers.facebook.com
  2. Add a phone number and generate a permanent access token
  3. Configure the webhook URL in Meta App Dashboard:
       https://<your-api>/v1/ai-clone/whatsapp/webhook/<uid>
     with any verify token that matches WHATSAPP_VERIFY_TOKEN below

Required env vars:
  WHATSAPP_PHONE_NUMBER_ID  — from Meta Business Suite
  WHATSAPP_ACCESS_TOKEN     — permanent token from Meta App
  WHATSAPP_VERIFY_TOKEN     — any string you choose (must match Meta dashboard)
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_GRAPH_URL = 'https://graph.facebook.com/v19.0'

PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '')
ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN', '')
VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', '')


async def send_message(to: str, text: str) -> bool:
    """
    Send a text message to `to` (E.164 phone number, e.g. +15551234567)
    via the WhatsApp Cloud API. Returns True on success.
    """
    if not PHONE_NUMBER_ID or not ACCESS_TOKEN:
        logger.warning('WhatsApp not configured — set WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN')
        return False

    url = f'{_GRAPH_URL}/{PHONE_NUMBER_ID}/messages'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    payload = {
        'messaging_product': 'whatsapp',
        'to': to.lstrip('+'),  # Meta expects no leading +
        'type': 'text',
        'text': {'body': text},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error(f'WhatsApp API error {resp.status_code}: {resp.text[:200]}')
                return False
            return True
    except Exception as e:
        logger.error(f'WhatsApp send_message exception: {e}')
        return False
