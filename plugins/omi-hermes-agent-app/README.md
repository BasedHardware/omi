# Hermes Agent for Omi

Connect Omi Chat Tools to a self-hosted [Hermes Agent](https://github.com/NousResearch/hermes-agent). Asking Omi to use `ask_hermes` creates a Hermes run, waits for the final answer, and returns it to Omi chat.

Hermes remains the agent and permission boundary: its selected profile controls the model, tools, memory, skills, and approval policy.

## Architecture

```text
Omi chat -> Omi Chat Tool -> this bridge -> Hermes Agent API server
```

The bridge does not store prompts or responses. It validates Omi `uid` and `app_id`, keeps the Hermes API key server-side, and never approves a pending Hermes tool action.

## 1. Prepare a dedicated Hermes profile

Install Hermes Agent and create a separate profile for Omi. Enable only the toolsets you want Omi chat to access. Use a restricted, proposal-only profile: prefer read-only tools, allow drafting or proposing changes instead of applying them, and require approval through Hermes for any consequential action.

Enable its API server in that profile's `.env`:

```env
API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
API_SERVER_KEY=replace-with-a-long-random-secret
```

Start the profile gateway and verify:

```bash
curl http://127.0.0.1:8642/health
curl http://127.0.0.1:8642/v1/capabilities \
  -H "Authorization: Bearer $API_SERVER_KEY"
```

See the authoritative [Hermes Agent API server documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server).

## 2. Run the bridge

Python 3.11 or newer is required (`asyncio.timeout` enforces the end-to-end run deadline). The included Dockerfile uses Python 3.12.

```bash
cd plugins/omi-hermes-agent-app
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env, then export its values with your preferred secret manager.
uvicorn main:app --host 127.0.0.1 --port 8000
```

Or build the included Dockerfile. When the bridge runs in a container, set `HERMES_API_URL` to an address from which the container can reach the host-side Hermes API server; do not expose Hermes itself publicly.

Required configuration:

| Variable | Purpose |
| --- | --- |
| `HERMES_API_KEY` | Bearer key for the Hermes API server |
| `OMI_ALLOWED_UIDS` | Comma-separated Omi user IDs accepted by the bridge |
| `OMI_ALLOWED_APP_IDS` | Comma-separated Omi app IDs accepted by the bridge |

Optional configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| `HERMES_API_URL` | `http://127.0.0.1:8642` | Hermes API server base URL |
| `HERMES_TIMEOUT_SECONDS` | `60` | Deadline for creating and polling a Hermes run; after expiry, the bridge allows up to 5 additional seconds to stop it cleanly |
| `HERMES_OMI_INSTRUCTIONS` | Safe concise Omi prompt | Instructions layered over the Hermes system prompt |

Both allowlists are mandatory. Missing allowlists fail closed with HTTP 503.

## 3. Give Omi a public HTTPS URL

Omi's backend invokes Chat Tools, so the bridge must be reachable from the public internet over HTTPS. Terminate TLS at a tunnel or reverse proxy and expose only this bridge. Keep the Hermes API on loopback or a private network; its port must not be internet-reachable.

Examples include Tailscale Funnel, Cloudflare Tunnel, or an HTTPS reverse proxy on your own server.

At the public edge, enforce a small request-body limit, rate-limit the tool endpoint, and ensure request bodies are never logged. This minimal Nginx example uses one global rate bucket, so it does not assume stable or unique Omi egress IPs:

```nginx
http {
    limit_req_zone $server_name zone=omi_bridge:10m rate=5r/s;

    server {
        listen 443 ssl;
        server_name your-bridge.example;
        ssl_certificate /path/to/fullchain.pem;
        ssl_certificate_key /path/to/privkey.pem;

        location = /tools/ask_hermes {
            client_max_body_size 32k;
            limit_req zone=omi_bridge burst=10 nodelay;
            access_log off;
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto https;
        }

        location / {
            proxy_pass http://127.0.0.1:8000;
        }
    }
}
```

Nginx's standard access log formats do not include request bodies; keep them that way and do not add `$request_body` to a custom log format or application/proxy logging. The endpoint-specific `access_log off` above is an additional safeguard. Tune the global rate for your expected traffic.

Verify the manifest:

```bash
curl https://your-bridge.example/.well-known/omi-tools.json
```

## 4. Create the private Omi app

In Omi mobile:

1. Open **Explore -> Create an App**.
2. Choose an integration app.
3. Set the app home URL to `https://your-bridge.example/`.
4. Set the Chat Tools manifest URL to `https://your-bridge.example/.well-known/omi-tools.json`.
5. Keep the app private while testing.
6. Put the generated app ID in `OMI_ALLOWED_APP_IDS` and restart the bridge.
7. Install the private app and ask Omi: `Ask Hermes what it can help me with.`

The manifest exposes one tool: `ask_hermes(request)`.

## Security notes

- **Use a dedicated Hermes profile.** The Hermes API can use every tool enabled for that profile, including terminal and file tools.
- **Do not expose the Hermes API server directly.** Only expose this narrow bridge.
- **Approvals are never granted by the bridge.** If a run enters `waiting_for_approval`, the bridge stops it and tells the user to confirm in Hermes.
- **Omi Chat Tool calls are not currently signed.** UID and app ID are caller-supplied routing identifiers and defense-in-depth filters, not cryptographic authentication. They do not prove that a request came from Omi. Until Omi provides signed requests, keep Hermes private, use the dedicated restricted/proposal-only profile, and enforce body and rate limits at the public edge.
- **Terminate TLS at the public edge.** Do not serve the bridge over plaintext internet connections, log request bodies, or forward public traffic directly to Hermes.
- Keep the app private until end-to-end behavior and permissions have been reviewed.

## Test

```bash
python -m unittest -v test_main.py
```
