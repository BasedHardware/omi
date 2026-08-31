#!/usr/bin/env bash
#
# Live E2E for the on-prem CHAT LLM path on KUBERNETES, driven from OUTSIDE the cluster.
#
# The compose twin (deploy/onprem/run-chat-e2e.sh) exercises the same chain locally; this one proves
# the Helm target, which had no chat E2E at all until the chart grew an llm_gateway workload:
#
#   external client -> LoadBalancer (MetalLB) -> Envoy Gateway -> backend (agentic)
#     -> omi:auto:<feature> LANE -> in-cluster llm-gateway (resolves lane -> model)
#     -> operator's OpenAI-compatible endpoint -> streamed answer
#
# "Outside" is meant literally: the request is issued from a container in its own network namespace,
# so it leaves the host and comes back through the LoadBalancer exactly as a phone on the LAN would.
# Running curl on the node itself would traverse the LB too, but it would not prove reachability for
# anything that is not the node.
#
# It also asserts the NEGATIVE half, which is the part worth having: the gateway must NOT be reachable
# from outside. Inference is an authenticated capability of the backend, not a service on the edge.
#
# Prerequisites:
#   1. the cluster is up with the chat profile and the gateway enabled:
#        --set chat.enabled=true --set chat.llmGateway.enabled=true
#        --set chat.llmGateway.serviceToken=<openssl rand -hex 24>
#        --set inference.openai.baseUrl=<your endpoint> --set inference.openai.apiKey=<placeholder ok>
#      (the local endpoint ignores the key, but the gateway requires one and reports its absence as
#       invalid_config — a silent 503 on every chat turn);
#   2. the auth profile is on and the realm has the omi-test direct-access client (dev/test realm);
#   3. your endpoint serves the model in chat.llmGateway.model.
#
# Usage:  ENTRY_IP=<loadBalancerIP> deploy/onprem/helm/run-chat-e2e-k0s.sh
set -euo pipefail

ENTRY_IP="${ENTRY_IP:-192.168.100.190}"
CLIENT_IMAGE="${CLIENT_IMAGE:-omi-oss-backend-test}"
REALM="${REALM:-omi}"
TEST_CLIENT="${TEST_CLIENT:-omi-test}"
TEST_USER="${TEST_USER:-testuser}"
TEST_PASS="${TEST_PASS:-testpass}"

log() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
fail() { printf '\033[31mFAIL: %s\033[0m\n' "$*"; exit 1; }

log "real OIDC token from the in-cluster Keycloak (client $TEST_CLIENT)"
TOKEN="$(curl -sk -X POST "https://$ENTRY_IP/realms/$REALM/protocol/openid-connect/token" \
  -d grant_type=password -d "client_id=$TEST_CLIENT" -d "username=$TEST_USER" -d "password=$TEST_PASS" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))')"
[ -n "$TOKEN" ] || fail "no access token — is the auth profile on and the realm the dev/test variant?"
echo "  token: ${#TOKEN} chars"

log "chat turn from an EXTERNAL client (own network namespace, out over the LAN)"
ANSWER="$(docker run --rm --network bridge -e TOKEN="$TOKEN" -e ENTRY_IP="$ENTRY_IP" "$CLIENT_IMAGE" /bin/sh -c '
  curl -sk -N -X POST "https://$ENTRY_IP/v2/messages" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"text\":\"In one short sentence: confirm inference reached you.\"}" --max-time 240 \
  | grep -m1 "^done: " | sed "s/^done: //" \
  | /opt/venv/bin/python -c "import sys,base64,json; s=sys.stdin.read().strip(); s+=\"=\"*(-len(s)%4); print(json.loads(base64.b64decode(s))[\"text\"])"
')"
printf '  ANSWER: %s\n' "$ANSWER"
[ -n "$ANSWER" ] || fail "no assistant answer in the stream"

# A non-empty answer is not proof: a failed LLM call comes back as a canned apology on the same stream.
case "$ANSWER" in
  *"Sorry, I encountered an error"* | *"I encountered an error"* | *"try again"*)
    fail "chat returned its canned error reply — the LLM call failed. Check:
      * kubectl logs -n omi deploy/llm-gateway  (invalid_config => missing OPENAI_API_KEY;
        401 => chat.llmGateway.serviceToken differs from the one the backend got);
      * the gateway pod actually restarted after the last value change (it checksums the Secret, but a
        hand-edited Secret needs a rollout restart);
      * the operator endpoint serves chat.llmGateway.model."
    ;;
esac

log "the gateway must NOT be reachable from outside — inference is a backend capability, not an edge service"
docker run --rm --network bridge -e ENTRY_IP="$ENTRY_IP" "$CLIENT_IMAGE" /bin/sh -c '
  code="$(curl -s -m 6 -o /dev/null -w "%{http_code}" "http://$ENTRY_IP:9080/health" || true)"
  [ "$code" = "000" ] || { echo "  gateway answered $code on the edge"; exit 1; }
  echo "  :9080 on the entry point: no response (correct)"
' || fail "the llm-gateway is exposed on the edge — it must stay a ClusterIP service"

log "and the backend still refuses an unauthenticated chat"
CODE="$(curl -sk -m 10 -o /dev/null -w '%{http_code}' -X POST "https://$ENTRY_IP/v2/messages" \
  -H 'Content-Type: application/json' -d '{"text":"x"}')"
[ "$CODE" = "401" ] || fail "unauthenticated POST /v2/messages returned $CODE, expected 401"
echo "  unauthenticated -> 401"

log "PASS — on-prem chat on Kubernetes, driven from outside, served by the operator's model"
