# 👓 ApexGlass: Solana Pay & Optical QR Settlement Helper for Omi AI Wearables

[![Omi Plugin](https://img.shields.io/badge/BasedHardware-Omi_Plugin-purple.svg)](https://github.com/BasedHardware/omi)
[![Solana Pay](https://img.shields.io/badge/Solana-Pay_v1.0-14F195.svg)](https://solanapay.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

Zero-custody Solana Pay optical QR parsing, audio prompt synthesis, and on-chain transaction verification plugin for **BasedHardware Omi** AI smart necklaces and smart glasses (`omiGlass`).

---

## 🏗️ Architecture & Interaction Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as 👤 Wearer (Omi Glasses)
    participant Glass as 👓 Omi Camera / Mic
    participant App as ⚡ ApexGlass Plugin (FastAPI)
    participant Wallet as 📱 Mobile Wallet (Phantom/Solflare)
    participant RPC as 🌐 Solana Cluster (Mainnet/Devnet)
    participant Merch as 🏪 Merchant POS / Terminal

    Merch->>Glass: Displays Solana Pay QR Code
    Glass->>App: Sends captured URI (solana:...)
    App->>App: Validates & parses recipient, amount, SPL token & memo
    App-->>Glass: Returns TTS Dialogue ("Pay 4.5 USDC to Coffee Roasters. Open wallet to approve.")
    Glass->>User: Speaks advisory voice prompt
    User->>Wallet: Approves & signs transaction in mobile wallet
    Wallet->>RPC: Broadcasts signed transaction
    RPC-->>Wallet: Returns transaction signature
    Glass->>App: /tools/verify_transaction_signature(signature)
    App->>RPC: getSignatureStatuses RPC query
    RPC-->>App: Confirmed / Finalized status
    App-->>Glass: Returns confirmed status & explorer URL
```

---

## 🚀 Key Features & Available Omi Chat Tools

| Omi Chat Tool | Method | Description |
| :--- | :--- | :--- |
| **`check_solana_balance`** | `POST` | Queries real-time SOL and lamport balances on Solana Mainnet or Devnet for any base58 address. |
| **`parse_solana_pay_request`** | `POST` | Decodes standard Solana Pay QR codes (`solana:<recipient>?amount=...&label=...&memo=...`) into structured payment parameters. |
| **`generate_payment_intent`** | `POST` | Generates conversational speech prompts for Omi's microphone and TTS speaker (*"Say 'Confirm' to approve"*). |
| **`verify_transaction_signature`** | `POST` | Queries Solana JSON-RPC to check transaction finality status and returns Solscan explorer URLs. |

---

## 💻 Local Development & Studio

### 1. Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run the Interactive Studio
```bash
uvicorn main:app --reload --port 8080
```
Open **`http://localhost:8080/`** to access the **ApexGlass Visual Studio** featuring:
- **Optical Viewfinder**: Live simulated camera viewfinder with animated laser reticle.
- **Voice Dialogue Player**: Native speech synthesis (Web Speech API) speaking confirmation prompts out loud.
- **On-Chain Balance Inspector**: Instant queries against live Solana public RPCs.

---

## 🧪 Test Verification

Run the test suite:

```bash
# Run unit tests
python -m unittest test_solana_pay.py

# Run end-to-end smoke test
python smoke_test.py
```

---

## 🔒 Safety & Security Guarantees

* **Zero Private Key Exposure**: The plugin operates strictly as a read-only parser and payment request synthesizer. It never touches, stores, or requests user private keys or seed phrases.
* **Base58 Cryptographic Bounds**: Every address and signature is validated against Solana base58 character constraints before dispatching RPC calls.
* **Strict Network Validation**: Rejects unrecognized network parameters outside `mainnet` and `devnet` with clear error responses.
* **Malformed Input Protection**: Strict sanitization of optical scan noise, negative amounts, control characters, and invalid protocols.
