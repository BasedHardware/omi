"""Solana Pay & Crypto Settlement App for BasedHardware Omi AI Wearables.

Enables hands-free Solana wallet queries, optical Solana Pay QR code resolution,
voice-confirmed micro-settlements, and on-chain transaction verification
directly from Omi AI necklaces and smart glasses.
"""

from contextlib import asynccontextmanager
import math
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    ChatToolResponse,
    CheckSolanaBalanceRequest,
    ParseSolanaPayRequest,
    SimulatePaymentVoiceIntentRequest,
    VerifyTransactionRequest,
)

SOLANA_RPC_URLS = {
    "mainnet": "https://api.mainnet-beta.solana.com",
    "devnet": "https://api.devnet.solana.com",
}
REQUEST_TIMEOUT_SECONDS = 12.0
BASE58_ALPHABET = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    headers = {"Content-Type": "application/json", "User-Agent": "Omi-SolanaPay-App/1.0"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi Solana Pay & Crypto Settlement App",
    description="Hands-free Solana wallet balance, Solana Pay QR resolution, and voice settlement for Omi AI wearables.",
    version="1.0.0",
    lifespan=lifespan,
)


def _is_valid_base58_address(addr: str) -> bool:
    """Validate that a string conforms to Solana base58 public key format."""
    if not isinstance(addr, str):
        return False
    clean = addr.strip()
    if not (32 <= len(clean) <= 44):
        return False
    return set(clean).issubset(BASE58_ALPHABET)


async def _solana_rpc_call(
    client: httpx.AsyncClient,
    method: str,
    params: list,
    network: str = "mainnet",
) -> Dict[str, Any]:
    """Execute a JSON-RPC call against public Solana clusters."""
    url = SOLANA_RPC_URLS.get(network.lower(), SOLANA_RPC_URLS["mainnet"])
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"error": {"message": str(exc)}}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=200,
        content=ChatToolResponse(
            result=None,
            error=f"Invalid request parameters: {exc.errors()}",
            data=None,
        ).model_dump(),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "app": "omi-solana-pay-app", "version": "1.0.0"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools_manifest():
    """Return standard Omi chat tool manifest for tool registry."""
    return {
        "tools": [
            {
                "name": "check_solana_balance",
                "description": "Check the real-time SOL balance of a Solana wallet address on mainnet or devnet.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "wallet_address": {
                            "type": "string",
                            "description": "Solana base58 wallet address to query.",
                        },
                        "network": {
                            "type": "string",
                            "enum": ["mainnet", "devnet"],
                            "default": "mainnet",
                            "description": "Solana network cluster ('mainnet' or 'devnet').",
                        },
                    },
                    "required": ["wallet_address"],
                },
            },
            {
                "name": "parse_solana_pay_request",
                "description": "Parse and decode a Solana Pay QR code string or payment URL into structured transaction details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "solana_pay_url": {
                            "type": "string",
                            "description": "The raw Solana Pay URI (e.g. solana:<recipient>?amount=...)",
                        },
                    },
                    "required": ["solana_pay_url"],
                },
            },
            {
                "name": "generate_payment_intent",
                "description": "Generate natural voice-confirmation dialogue for Omi wearable speaker before executing a crypto transfer.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "recipient": {
                            "type": "string",
                            "description": "Recipient merchant name or wallet address.",
                        },
                        "amount": {
                            "type": "number",
                            "description": "Payment amount.",
                        },
                        "currency": {
                            "type": "string",
                            "default": "USDC",
                            "description": "Currency or token symbol ('USDC', 'SOL').",
                        },
                        "memo": {
                            "type": "string",
                            "description": "Optional order memo or description.",
                        },
                    },
                    "required": ["recipient", "amount"],
                },
            },
            {
                "name": "verify_transaction_signature",
                "description": "Verify whether a Solana transaction has been confirmed or finalized on-chain.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "signature": {
                            "type": "string",
                            "description": "Solana base58 transaction signature.",
                        },
                        "network": {
                            "type": "string",
                            "enum": ["mainnet", "devnet"],
                            "default": "mainnet",
                            "description": "Solana cluster to query.",
                        },
                    },
                    "required": ["signature"],
                },
            },
        ]
    }


@app.post("/tools/check_solana_balance", response_model=ChatToolResponse)
async def check_solana_balance(req: CheckSolanaBalanceRequest):
    addr = req.wallet_address.strip()
    if not _is_valid_base58_address(addr):
        return ChatToolResponse(
            error=f"Invalid Solana wallet address '{addr}'. Expected base58 string between 32 and 44 characters."
        )

    network = req.network.lower() if req.network else "mainnet"
    client = app.state.http_client

    rpc_resp = await _solana_rpc_call(
        client,
        "getBalance",
        [addr, {"commitment": "confirmed"}],
        network=network,
    )

    if "error" in rpc_resp:
        return ChatToolResponse(
            error=f"Solana RPC error: {rpc_resp['error'].get('message', 'Unknown error')}"
        )

    result_val = rpc_resp.get("result", {}).get("value", 0)
    sol_balance = result_val / 1_000_000_000.0

    cluster_name = "Solana Mainnet" if network == "mainnet" else "Solana Devnet"
    short_addr = f"{addr[:4]}...{addr[-4:]}"
    human_text = f"Wallet {short_addr} balance on {cluster_name}: {sol_balance:.4f} SOL ({result_val:,} lamports)."

    return ChatToolResponse(
        result=human_text,
        data={
            "address": addr,
            "sol_balance": sol_balance,
            "lamports": result_val,
            "network": network,
        },
    )


@app.post("/tools/parse_solana_pay_request", response_model=ChatToolResponse)
async def parse_solana_pay_request(req: ParseSolanaPayRequest):
    raw_url = req.solana_pay_url.strip()
    if not raw_url.startswith("solana:"):
        return ChatToolResponse(
            error="Invalid Solana Pay URI: scheme must begin with 'solana:'."
        )

    clean_uri = raw_url[len("solana:") :]
    if "?" in clean_uri:
        recipient, query_string = clean_uri.split("?", 1)
    else:
        recipient, query_string = clean_uri, ""

    recipient = unquote(recipient).strip()
    if not _is_valid_base58_address(recipient):
        return ChatToolResponse(
            error=f"Invalid recipient public key in Solana Pay URI: '{recipient}'."
        )

    params = parse_qs(query_string)
    amount_str = params.get("amount", [None])[0]
    raw_label = unquote(params.get("label", ["Merchant"])[0])
    raw_message = unquote(params.get("message", [""])[0]) if params.get("message") else None
    raw_memo = unquote(params.get("memo", [""])[0]) if params.get("memo") else None
    reference = params.get("reference", [None])[0]
    spl_token = params.get("spl-token", [None])[0]

    # Sanitize and bound text parameters (strip non-printable/control chars, limit length)
    label = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', raw_label)[:64].strip() or "Merchant"
    message = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', raw_message)[:256].strip() if raw_message else None
    memo = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', raw_memo)[:128].strip() if raw_memo else None

    # Validate reference pubkey if provided
    if reference and not _is_valid_base58_address(reference):
        return ChatToolResponse(error=f"Invalid reference public key in Solana Pay URI: '{reference}'.")

    # Validate SPL token mint if provided
    if spl_token and not _is_valid_base58_address(spl_token):
        return ChatToolResponse(error=f"Invalid spl-token mint address in Solana Pay URI: '{spl_token}'.")

    amount = None
    if amount_str:
        try:
            amount = float(amount_str)
            if math.isnan(amount) or math.isinf(amount) or amount < 0:
                return ChatToolResponse(error="Amount in Solana Pay URI must be a finite, non-negative number.")
        except ValueError:
            return ChatToolResponse(error=f"Invalid numeric amount '{amount_str}' in Solana Pay URI.")

    token_type = "SOL"
    if spl_token:
        if spl_token == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":
            token_type = "USDC"
        else:
            token_type = f"SPL ({spl_token[:4]}...{spl_token[-4:]})"

    summary_parts = [f"Solana Pay Request: Pay {amount} {token_type}" if amount else "Solana Pay Request: Any Amount"]
    summary_parts.append(f"to {label} ({recipient[:4]}...{recipient[-4:]})")
    if message:
        summary_parts.append(f"— Message: '{message}'")
    if memo:
        summary_parts.append(f"— Memo: '{memo}'")

    voice_prompt = (
        f"Detected payment to {label} for {amount} {token_type}. Say 'Confirm' to approve."
        if amount
        else f"Detected payment to {label}. Please state the amount to proceed."
    )

    return ChatToolResponse(
        result=" ".join(summary_parts),
        data={
            "recipient": recipient,
            "amount": amount,
            "token": token_type,
            "spl_token_mint": spl_token,
            "label": label,
            "message": message,
            "memo": memo,
            "reference": reference,
            "voice_prompt": voice_prompt,
        },
    )


@app.post("/tools/generate_payment_intent", response_model=ChatToolResponse)
async def generate_payment_intent(req: SimulatePaymentVoiceIntentRequest):
    curr = req.currency.upper() if req.currency else "USDC"
    speech = (
        f"You are about to send {req.amount:g} {curr} to {req.recipient}. "
        f"Say 'Confirm' to authorize payment, or 'Cancel' to abort."
    )
    if req.memo:
        speech += f" Reference memo: {req.memo}."

    return ChatToolResponse(
        result=speech,
        data={
            "recipient": req.recipient,
            "amount": req.amount,
            "currency": curr,
            "memo": req.memo,
            "tts_speech": speech,
            "approval_phrase": "confirm",
            "cancel_phrase": "cancel",
        },
    )


@app.post("/tools/verify_transaction_signature", response_model=ChatToolResponse)
async def verify_transaction_signature(req: VerifyTransactionRequest):
    sig = req.signature.strip()
    if not (64 <= len(sig) <= 128) or not set(sig).issubset(BASE58_ALPHABET):
        return ChatToolResponse(
            error=f"Invalid Solana signature '{sig}'. Expected base58 transaction signature."
        )

    network = req.network.lower() if req.network else "mainnet"
    client = app.state.http_client

    rpc_resp = await _solana_rpc_call(
        client,
        "getSignatureStatuses",
        [[sig], {"searchTransactionHistory": True}],
        network=network,
    )

    if "error" in rpc_resp:
        return ChatToolResponse(
            error=f"RPC error verifying signature: {rpc_resp['error'].get('message', 'Unknown error')}"
        )

    statuses = rpc_resp.get("result", {}).get("value", [None])
    status_obj = statuses[0] if statuses else None

    if not status_obj:
        return ChatToolResponse(
            result=f"Transaction {sig[:8]}...{sig[-8:]} is pending or not found on {network}.",
            data={"signature": sig, "confirmed": False, "status": "not_found"},
        )

    confirmation = status_obj.get("confirmationStatus", "unknown")
    err = status_obj.get("err")
    slot = status_obj.get("slot")

    if err:
        return ChatToolResponse(
            result=f"Transaction failed on {network} at slot {slot}: {err}",
            data={"signature": sig, "confirmed": False, "error": err, "slot": slot},
        )

    explorer_url = (
        f"https://solscan.io/tx/{sig}"
        if network == "mainnet"
        else f"https://solscan.io/tx/{sig}?cluster=devnet"
    )

    return ChatToolResponse(
        result=f"Transaction confirmed on {network}! Status: {confirmation} (Slot {slot}). Explorer: {explorer_url}",
        data={
            "signature": sig,
            "confirmed": True,
            "confirmation_status": confirmation,
            "slot": slot,
            "explorer_url": explorer_url,
        },
    )


@app.get("/", response_class=HTMLResponse)
async def home():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ApexGlass — Omi AI Wearable Solana Pay Studio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090b10;
      --card-bg: rgba(22, 27, 34, 0.7);
      --border: rgba(255, 255, 255, 0.08);
      --sol-purple: #9945FF;
      --sol-green: #14F195;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --glow: rgba(153, 69, 255, 0.15);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Outfit', sans-serif;
      background: radial-gradient(circle at 50% -20%, #1e1035 0%, var(--bg) 70%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 40px 20px;
    }
    .container { max-width: 900px; width: 100%; }
    .header {
      text-align: center;
      margin-bottom: 40px;
    }
    .badge-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px;
      background: rgba(153, 69, 255, 0.12);
      border: 1px solid rgba(153, 69, 255, 0.3);
      border-radius: 9999px;
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--sol-green);
      margin-bottom: 16px;
      letter-spacing: 0.5px;
    }
    .header h1 {
      font-size: 2.8rem;
      font-weight: 700;
      background: linear-gradient(135deg, #fff 40%, var(--sol-green) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 12px;
    }
    .header p { color: var(--text-muted); font-size: 1.15rem; max-width: 600px; margin: 0 auto; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 24px; margin-bottom: 30px; }
    .card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 24px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
      transition: transform 0.2s, border-color 0.2s;
    }
    .card:hover { border-color: rgba(153, 69, 255, 0.4); transform: translateY(-2px); }
    .card-title {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 1.25rem;
      font-weight: 600;
      margin-bottom: 16px;
      color: #fff;
    }
    .card-title span.icon { font-size: 1.4rem; }
    .viewfinder-box {
      position: relative;
      width: 100%;
      height: 180px;
      background: #0d1117;
      border: 2px dashed rgba(20, 241, 149, 0.3);
      border-radius: 12px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      margin-bottom: 16px;
    }
    .scan-line {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 3px;
      background: linear-gradient(90deg, transparent, var(--sol-green), transparent);
      box-shadow: 0 0 15px var(--sol-green);
      animation: scan 2.4s infinite ease-in-out;
    }
    @keyframes scan { 0% { top: 5%; } 50% { top: 90%; } 100% { top: 5%; } }
    .input-group { margin-bottom: 14px; }
    .input-group label { display: block; font-size: 0.85rem; color: var(--text-muted); margin-bottom: 6px; font-weight: 500; }
    .input-field {
      width: 100%;
      background: rgba(13, 17, 23, 0.8);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 14px;
      color: #fff;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.88rem;
      outline: none;
      transition: border-color 0.2s;
    }
    .input-field:focus { border-color: var(--sol-green); }
    .btn {
      width: 100%;
      background: linear-gradient(135deg, var(--sol-purple), #7928ca);
      color: #fff;
      border: none;
      border-radius: 10px;
      padding: 12px;
      font-weight: 600;
      font-size: 0.95rem;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: opacity 0.2s, box-shadow 0.2s;
    }
    .btn:hover { opacity: 0.92; box-shadow: 0 0 20px var(--glow); }
    .btn-green {
      background: linear-gradient(135deg, #10b981, #059669);
    }
    .result-box {
      margin-top: 14px;
      padding: 12px;
      background: rgba(0, 0, 0, 0.3);
      border-radius: 8px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      color: #38bdf8;
      word-break: break-all;
      min-height: 44px;
      display: flex;
      align-items: center;
    }
    .footer { text-align: center; margin-top: 30px; color: var(--text-muted); font-size: 0.9rem; }
    .footer a { color: var(--sol-green); text-decoration: none; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="badge-pill">⚡ BASED HARDWARE OMI &bull; OFFICIAL PLUGIN</div>
      <h1>👓 ApexGlass Solana Pay Studio</h1>
      <p>Autonomous Solana Pay QR Optical Scanning & Voice Micro-Settlement for Omi Smart Glasses and Necklaces.</p>
    </div>

    <div class="grid">
      <!-- Card 1: Optical QR Viewfinder -->
      <div class="card">
        <div class="card-title">
          <span class="icon">📷</span>
          <span>Optical Solana Pay Scanner</span>
        </div>
        <div class="viewfinder-box">
          <div class="scan-line"></div>
          <span style="font-size: 2.5rem; opacity: 0.6;">🎯</span>
          <span style="font-size: 0.8rem; color: var(--sol-green); margin-top: 6px; font-weight: 600;">ACTIVE OMI GLASSES VIEW</span>
        </div>
        <div class="input-group">
          <label>Solana Pay URI / QR Target</label>
          <input type="text" id="solanaPayUri" class="input-field" value="solana:FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8?amount=4.50&spl-token=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&label=Coffee%20Roasters&memo=Order%2312">
        </div>
        <button class="btn" onclick="decodeSolanaPay()">Decode QR & Trigger Voice Dialogue</button>
        <div class="result-box" id="decodeResult">Ready for optical scan...</div>
      </div>

      <!-- Card 2: Voice Dialogue & Audio Synthesis -->
      <div class="card">
        <div class="card-title">
          <span class="icon">🎙️</span>
          <span>Wearable Voice Audio Engine</span>
        </div>
        <div class="input-group">
          <label>Recipient Merchant</label>
          <input type="text" id="voiceRecipient" class="input-field" value="Coffee Roasters">
        </div>
        <div class="input-group">
          <label>Transfer Amount (USDC / SOL)</label>
          <input type="number" id="voiceAmount" class="input-field" value="4.50" step="0.1">
        </div>
        <button class="btn btn-green" onclick="speakConfirmation()">🔊 Synthesize & Speak Omi Dialogue</button>
        <div class="result-box" id="voiceResult">Click button to hear wearable audio confirmation.</div>
      </div>

      <!-- Card 3: Real-Time Balance Query -->
      <div class="card">
        <div class="card-title">
          <span class="icon">💳</span>
          <span>Live Solana On-Chain Balance</span>
        </div>
        <div class="input-group">
          <label>Wallet Address</label>
          <input type="text" id="walletAddr" class="input-field" value="FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8">
        </div>
        <div class="input-group">
          <label>Cluster</label>
          <select id="clusterSelect" class="input-field" style="height: 42px;">
            <option value="mainnet">Solana Mainnet</option>
            <option value="devnet" selected>Solana Devnet</option>
          </select>
        </div>
        <button class="btn" onclick="queryBalance()">Query Live Balance</button>
        <div class="result-box" id="balanceResult">Querying Solana public RPC...</div>
      </div>

      <!-- Card 4: Architecture & Manifest -->
      <div class="card">
        <div class="card-title">
          <span class="icon">⚙️</span>
          <span>Omi Ecosystem Registry</span>
        </div>
        <p style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 16px;">
          This service exposes standardized chat tools matching BasedHardware's plugin specifications:
        </p>
        <ul style="font-size: 0.85rem; color: var(--sol-green); margin-left: 20px; line-height: 1.8;">
          <li><code>check_solana_balance</code> (Live RPC)</li>
          <li><code>parse_solana_pay_request</code> (Optical QR)</li>
          <li><code>generate_payment_intent</code> (TTS Prompt)</li>
          <li><code>verify_transaction_signature</code> (Finality)</li>
        </ul>
        <div style="margin-top: 20px; display: flex; gap: 10px;">
          <a href="/.well-known/omi-tools.json" target="_blank" class="btn" style="text-decoration: none; font-size: 0.85rem;">View Tool Manifest JSON</a>
          <a href="/docs" target="_blank" class="btn btn-green" style="text-decoration: none; font-size: 0.85rem;">OpenAPI Swagger</a>
        </div>
      </div>
    </div>

    <div class="footer">
      Built for <strong>BasedHardware Omi & omiGlass</strong> &bull; Open-source under MIT License &bull; <a href="https://github.com/pullitall/omi" target="_blank">@pullitall/omi</a>
    </div>
  </div>

  <script>
    async function decodeSolanaPay() {
      const url = document.getElementById('solanaPayUri').value;
      const resBox = document.getElementById('decodeResult');
      resBox.innerText = 'Decoding QR payload...';
      try {
        const resp = await fetch('/tools/parse_solana_pay_request', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({solana_pay_url: url})
        });
        const d = await resp.json();
        if (d.error) {
          resBox.style.color = '#ef4444';
          resBox.innerText = 'Error: ' + d.error;
        } else {
          resBox.style.color = '#14F195';
          resBox.innerText = d.result;
          if (d.data && d.data.voice_prompt && 'speechSynthesis' in window) {
            const utter = new SpeechSynthesisUtterance(d.data.voice_prompt);
            utter.rate = 1.05;
            window.speechSynthesis.speak(utter);
          }
        }
      } catch (e) {
        resBox.innerText = 'Network error: ' + e;
      }
    }

    async function speakConfirmation() {
      const rec = document.getElementById('voiceRecipient').value;
      const amt = parseFloat(document.getElementById('voiceAmount').value);
      const resBox = document.getElementById('voiceResult');
      try {
        const resp = await fetch('/tools/generate_payment_intent', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({recipient: rec, amount: amt, currency: 'USDC'})
        });
        const d = await resp.json();
        resBox.innerText = d.result;
        if ('speechSynthesis' in window) {
          const utter = new SpeechSynthesisUtterance(d.result);
          window.speechSynthesis.speak(utter);
        }
      } catch (e) {
        resBox.innerText = 'Error: ' + e;
      }
    }

    async function queryBalance() {
      const addr = document.getElementById('walletAddr').value;
      const net = document.getElementById('clusterSelect').value;
      const resBox = document.getElementById('balanceResult');
      resBox.innerText = 'Fetching on-chain balance from ' + net + '...';
      try {
        const resp = await fetch('/tools/check_solana_balance', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({wallet_address: addr, network: net})
        });
        const d = await resp.json();
        if (d.error) {
          resBox.style.color = '#ef4444';
          resBox.innerText = d.error;
        } else {
          resBox.style.color = '#14F195';
          resBox.innerText = d.result;
        }
      } catch (e) {
        resBox.innerText = 'RPC Error: ' + e;
      }
    }
  </script>
</body>
</html>
"""
