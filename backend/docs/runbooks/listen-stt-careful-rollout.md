# Listen recovery: coordinator rollout card (#20391)

**Coordinator runs every cluster/build action. HOLD until Luna has reviewed the
final #20391 diff and its default-off recovery flag. No production action was
performed when writing this card.** Commands run from the repository root.
Keep routing shadow/on0, provider order and allocations unchanged in prod.
The [design/image notes](listen-stt-canary-design.md), [soak instructions](../../../testing/live_stt_soak/README.md)
and [watch queries](listen-stt-canary-queries.promql) are part of this card.

1. **Merge inert code, locate image.** #20391's author must implement and test
   `STT_FAILOVER_RECOVERY_ENABLED=false` as the code/chart/runtime default;
   this is a proposed name, not an existing switch. It must cover controller,
   replay, adapter and rejection changes, not just routing. Approve that diff
   first. Merge through normal PRs, wait for successful main Release Eligibility,
   then use the existing dev build. It deploys dev surfaces; it is not build-only.

   ```bash
   export RELEASE_SHA=<full-merged-eligible-main-sha>
   gh workflow run gcp_backend.yml --ref main -f environment=development \
     -f mode=deploy -f release_sha="$RELEASE_SHA" -f deploy_targets=cloud-run-only
   # Locate this exact run with gh run list, then gh run watch RUN_ID --exit-status.
   export TAG=$(git rev-parse --short=7 "$RELEASE_SHA")
   source ~/.local/bin/gcp-agent-env.sh ro-dev
   export DIGEST=$(gcloud container images describe "gcr.io/based-hardware-dev/backend:$TAG" \
     --project based-hardware-dev --format='value(image_summary.digest)')
   export IMAGE="gcr.io/based-hardware-dev/backend@$DIGEST"
   test -n "$DIGEST"
   ```

   Coordinator must confirm prod node pull permission for this dev image digest
   without granting IAM, and inspect exact image source/flag. If unavailable,
   use an **already built** prod image for the same merged SHA. The prod build
   also promotes Cloud Run, so obtain that separately scoped release approval;
   do not use it as an unapproved image factory. Rollback: stop here; no listen
   mutation. Never bypass eligibility to build a PR head.

2. **Dev soak and rollback drill.** Follow the linked soak README: 16 public-audio
   sessions for 10 minutes in each window→Soniox and window→Modulate arm, fake
   first then paid if credentials/capacity permit. Review terminal failures,
   positive replay coverage, wall time/skips/recovered/exhausted, RSS, paid usage
   and backfill headroom. Missing exposure means HOLD. Delete the isolated dev
   namespace to stop the soak. Record fake versus vendor evidence separately.

3. **Two-pod prod canary.** Set explicit coordinator context from the approved
   cluster inventory; never rely on the default. Capture controls, then render,
   review, diff, apply and check ready Service endpoints/NEG health and scrapes.

   ```bash
   export PROD_CTX=gke_based-hardware_us-central1_prod-omi-gke
   export NS=prod-omi-backend
   source ~/.local/bin/gcp-agent-env.sh prod-operator
   kubectl --context "$PROD_CTX" -n "$NS" get deploy prod-omi-backend-listen -o yaml > /tmp/listen-control.yaml
   kubectl --context "$PROD_CTX" -n "$NS" get pods -l app.kubernetes.io/name=backend-listen -o json > /tmp/listen-controls.json
   backend/.venv/bin/python backend/scripts/render_listen_canary.py --environment prod \
     --image "$IMAGE" --replicas 2 --env STT_FAILOVER_RECOVERY_ENABLED=true > /tmp/listen-canary.yaml
   kubectl --context "$PROD_CTX" -n "$NS" diff -f /tmp/listen-canary.yaml
   # diff exit 1 means differences; any other nonzero status is an error.
   kubectl --context "$PROD_CTX" -n "$NS" apply -f /tmp/listen-canary.yaml
   kubectl --context "$PROD_CTX" -n "$NS" rollout status deployment/prod-omi-backend-listen-canary --timeout=10m
   kubectl --context "$PROD_CTX" -n "$NS" get pods -l track=canary -o wide
   kubectl --context "$PROD_CTX" -n "$NS" get endpointslice -l kubernetes.io/service-name=prod-omi-backend-listen -o yaml
   ```

   Two of 30–60 main pods gives approximately 3–6% of endpoints. LB connections
   are not guaranteed to follow that share: measure accepted sockets by exact
   canary pod names. Save the control digest; verify the reported `a2ab2c5`
   controls actually exist, otherwise HOLD/review the comparable-load baseline.
   Start the clock only after **both** canary pods are ready, NEG-attached and
   scraped. Refresh exact pod regex after replacements; reset the exposure
   window. Rollback at every canary stage is the same draining removal:

   ```bash
   kubectl --context "$PROD_CTX" -n "$NS" delete deployment prod-omi-backend-listen-canary --wait=true --timeout=5m
   ```

4. **15-minute gate.** From #20391 report §8: ≥10 positive-duration replays
   covering both paid families; all new pods scraped; zero paid capacity deaths
   or replay-induced 1011; replay p95 ≤20s with ≥10 observations; no unexplained
   fresh-audio skips; no lifecycle residual sustained 2min. Any-text success
   ≥95% with ≥50 sockets, decline ≤2 percentage points against simultaneous
   controls. Terminal-after-text zero, or individually review every non-replay
   cause. Recovered successor death = investigate/HOLD; replay-induced terminal
   death = ABORT/remove. Missing metrics or exposure = HOLD, never elapsed-time GO.

5. **60-minute gate.** ≥30 positive replays, ≥5 per paid family, ≥100 canary
   sockets; same zero-overflow/replay-terminal/lifecycle gates; fleet
   `omi_live_stt_terminal_failures_total{phase=~"connection|send"}` ≤3/25min
   at comparable load; first-text p95 <30s; window POST p95 <2s; combined
   pressure/overflow ≤1%/10min with ≥20 admissions. Review RSS slope/limit
   headroom, vendor usage, GPU and backfill queues. Fallback `exhausted` is a
   diagnostic, **not the authoritative user-harm count**. Two proposed watches
   in the query file have a 1min dwell; this PR installs no alert rules.

6. **Expand only after attended hour and coordinator approval.** For 25% then
   50% of endpoints (each ≥1h; 50% through peak), use `ceil(p*main_ready/(1-p))`
   fixed canary replicas, capacity-check first, regenerate the manifest with
   `--replicas COUNT`, then apply and repeat gates. Record actual socket share;
   HPA movement changes endpoint share. At 60 main pods, 50% needs 60 extra
   pods: insufficient headroom means HOLD. Rollback: draining removal above.

7. **Full rollout, then removal.** Enable the approved flag through a normal
   config PR in prod chart **and** runtime overlay and regenerate the runtime
   manifest; routine hourly main deploys otherwise overwrite a manual main
   env patch. Coordinator dispatches existing listen workflow with the admitted
   image's short SHA (prod registry image required), observes ≥1h and repeats
   gates, then removes canary with the command above. Keep canary until main
   is ready/scraped. For full-rollout containment, coordinate all release writers,
   revert the flag in those owning config sources and redeploy; if an immediate
   image rollback is needed, use the approved `0ba6edb` containment SHA below
   and remove active canary. It retains the old overflow defect. Pause/resume
   competing release writers by coordinator agreement; no workflow edits here.

   ```bash
   gh workflow run gcp_backend_listen_helm.yml --ref main -f environment=prod \
     -f branch=main -f mode=deploy -f image_tag="$TAG"
   # Emergency containment only after verifying this known tag exists in prod:
   gh workflow run gcp_backend_listen_helm.yml --ref main -f environment=prod \
     -f branch=main -f mode=deploy -f image_tag=0ba6edb
   ```

Deletion retains chart preStop (15s) and termination grace (120s). Existing
sockets remain process-owned; there is no cross-image session transfer. Grace
is bounded, not a promise that every long WebSocket ends naturally. Record
disconnects in the rollback drill; abrupt process death can lose in-memory tail.
