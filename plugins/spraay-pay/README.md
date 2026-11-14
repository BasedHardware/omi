# Spraay Pay — x402 USDC Payments for Omi

## What it does

Spraay Pay adds voice-initiated noncustodial USDC payments on Base to the Omi wearable, using the
x402 protocol. It is a self-hosted webhook server: the Omi backend calls it, and nothing runs on
the device.

Noncustodial here means you run the server and hold the key, so no third party holds your funds.
The configured wallet signs for every allowed user, so only allowlist people you trust with it
and keep your Omi apps private.

## How it works

Real-time transcript detection of payment intent → confirmation code → `/confirm` to execute.

1. You say "Pay $5 to api dot example dot com". Omi sends the transcript to `/webhook/transcript`.
   The request must include a service address; without one, the server asks you for it.
2. The server replies with a notification containing a 6-digit code:
   *pay $5.00 USDC to https://api.example.com? To approve, type /confirm 482913.*
3. You type `/confirm 482913` in Omi chat. Limits are rechecked before anything is sent.
4. The server requests the service, signs the x402 payment, and returns the transaction hash to chat.

You can also start a payment by typing `/pay $5 to api.example.com`, and drop pending payments
with `/cancel`.

| Endpoint | Called by | Purpose |
|---|---|---|
| `POST /webhook/transcript` | Omi `transcript_processed` | Detects payment intent, asks for confirmation |
| `POST /webhook/memory` | Omi `memory_creation` | Audit trail and recurring payment patterns |
| `POST /chat/pay` | Chat tool | `/pay $5 to api.example.com` |
| `POST /chat/confirm` | Chat tool | `/confirm 123456` |
| `POST /chat/cancel` | Chat tool | `/cancel` |
| `GET /.well-known/omi-tools.json` | Omi | Chat tools manifest |
| `GET /health` | You | Liveness check |

## Features

- **Spending limits:** per-payment and per-user daily limits, checked in the same database
  transaction that commits the spend.
- **Per-user auth:** every route needs the shared `?token=` secret, and only `ALLOWED_UIDS` can
  spend. An empty allowlist denies everyone.
- **Confirmation codes:** voice never pays directly. It needs a single-use, expiring code typed in
  chat, and only segments Omi marks as the wearer's own speech count.
- **SQLite ledger:** payments, pending confirmations, and the audit trail are stored in SQLite.
  Payments with an uncertain outcome stay counted against the daily limit.
- **Overcharge protection:** the confirmed amount is a hard cap. A service quoting more is
  refused, as is any other network or any token other than the network's USDC.

## Setup

### 1. Clone

```bash
git clone --depth=1 https://github.com/BasedHardware/omi.git
cd omi/plugins/spraay-pay
```

### 2. Install

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Fill in `.env` using the table below. Use a dedicated wallet that holds only what you are willing
to lose.

To run it locally and run the tests:

```bash
uvicorn main:app --port 8000 --no-access-log
pytest -v
```

### 4. Deploy

Build the `Dockerfile` and run it on any container host with a public https URL. Mount a
persistent volume at `/data`, otherwise daily limits and pending confirmations reset on every
deploy. Set the variables below in the host's environment.

```bash
docker build -t spraay-pay .
docker run -p 8000:8000 --env-file .env -v spraay-data:/data spraay-pay
```

The default network is Base Sepolia. Set `NETWORK=base` for mainnet, which spends real money.
Access logs stay off in the container because Omi URLs carry the shared secret. Rotate the secret
if a URL leaks.

### 5. Register in the Omi app

See [Registering as an Omi app](#registering-as-an-omi-app).

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `WALLET_PRIVATE_KEY` | Yes | None | Hex private key of the paying wallet. It signs for every allowed user. |
| `WEBHOOK_SECRET` | Yes | None | Long random string, added to every Omi URL as `?token=...` |
| `ALLOWED_UIDS` | Yes | Empty | Comma-separated Omi user IDs allowed to spend. Empty denies everyone. |
| `PUBLIC_BASE_URL` | Yes | `https://YOUR_ENDPOINT` | Public https URL of this server, used in the chat tools manifest. |
| `NETWORK` | No | `base-sepolia` | `base-sepolia` (testnet) or `base` (mainnet, real money). |
| `MAX_PER_PAYMENT_USD` | No | `5` | Largest single payment, in USD. |
| `DAILY_LIMIT_USD` | No | `20` | Most each user can spend per UTC day, in USD. |
| `AUTO_APPROVE_USD` | No | `0` | `/pay` amounts up to this run without a code. `0` confirms everything. Voice payments always need a code. |
| `PENDING_TTL_SECONDS` | No | `300` | Seconds a confirmation code stays valid. |
| `ALLOWED_DOMAINS` | No | Empty | Comma-separated domains that may be paid, subdomains included. Empty allows any public https service. Strongly recommended on mainnet. |
| `DATABASE_PATH` | No | `data/spraay.db` | SQLite file for the transaction log, confirmations, and audit trail. Must be on persistent storage. |

## Registering as an Omi app

Omi's `triggers_on` holds one value per app, so transcript and memory triggers need **two** apps.
Replace `YOUR_ENDPOINT` and `YOUR_WEBHOOK_SECRET` in `omi_app.json` and `omi_app_memory.json`, then
create one Omi app from each file, uploading a logo for each.

| App | Trigger | URL to set |
|---|---|---|
| Spraay Pay (`omi_app.json`) | `transcript_processed` webhook | `https://YOUR_ENDPOINT/webhook/transcript?token=YOUR_WEBHOOK_SECRET` |
| Spraay Pay (`omi_app.json`) | Chat tools manifest | `https://YOUR_ENDPOINT/.well-known/omi-tools.json?token=YOUR_WEBHOOK_SECRET` |
| Spraay Pay Audit (`omi_app_memory.json`) | `memory_creation` webhook | `https://YOUR_ENDPOINT/webhook/memory?token=YOUR_WEBHOOK_SECRET` |

Set `https://YOUR_ENDPOINT` as the app home URL for both. Omi appends `uid` to each webhook URL.
Add each user's Omi ID to `ALLOWED_UIDS`, and set up a speech profile so Omi can identify the
wearer's speech.

## Full SDK

- SDK: [plagtech/spraay-device-pay](https://github.com/plagtech/spraay-device-pay)
- npm package: [@plagtech/spraay-device-pay](https://www.npmjs.com/package/@plagtech/spraay-device-pay)

## Author

[Plagtech](https://github.com/plagtech)

## License

MIT
