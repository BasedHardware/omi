# LLM Gateway Image Ownership

## Symptom

An ordinary LLM gateway rollout fails in the `Deploy LLM Gateway to GKE cluster using Helm`
step, before the rollout wait:

```
Error: UPGRADE FAILED: conflict occurred while applying object prod-omi-backend/prod-omi-llm-gateway apps/v1, Kind=Deployment:
Apply failed with 1 conflict: conflict with "kubectl-patch" using apps/v1:
.spec.template.spec.containers[name="llm-gateway"].image
```

Helm 4 applies every chart object through server-side apply as field manager `helm`. Server-side
apply refuses to change a field that a different field manager owns, so the rollout stops with the
gateway still on the image it was serving.

## Cause

Someone changed the image with `kubectl patch` (or `kubectl set image`, `kubectl edit`) instead of
the Helm rollout. An image-only JSON patch is an `Update` that records a `kubectl-patch` managed-fields
entry owning only `.spec.template.spec.containers[name="llm-gateway"].image`, and Helm's entry loses
that leaf. Every later rollout that sets a different image conflicts. The conflict is on the
*ownership*, not the value: reapplying the same image through Helm does not return the leaf to Helm.

A separately authorized one-off image move leaves the same entry behind.

## What the deploy does about it

`backend/scripts/deploy-llm-gateway.sh` renders the Deployment with the exact arguments, image and
release name the rollout will use and sends it to the API server as a server-side dry-run under field
manager `helm`. That is the same request as the real apply without the write, so it reports the
conflict the real apply would hit.

The check runs before the shared backend secret reapply and again right before `helm upgrade
--install`. A failing check exits before anything is mutated: no secret write, no Helm release
change, no rollout. Install, the rollout wait and the immutable-image handling are unchanged.

## Who owns the image

Read-only:

```bash
NS=prod-omi-backend
RELEASE=prod-omi-llm-gateway
kubectl -n "$NS" get deployment "$RELEASE" --show-managed-fields -o json \
  | jq -c '.metadata.managedFields[]
      | select(.fieldsV1["f:spec"]["f:template"]["f:spec"]["f:containers"]["k:{\"name\":\"llm-gateway\"}"]["f:image"])
      | {manager, operation, time}'
```

An empty result means nobody owns the image and the next ordinary rollout applies without a
handoff. `kubectl get` omits managed fields unless `--show-managed-fields` is passed.

## Hand the image back to Helm

Production rollout and this ownership change belong to the release owner, under the normal
production authorization. `backend/scripts/handoff-llm-gateway-image-ownership.py` removes the one
`kubectl-patch` entry and nothing else, so the serving image, pod template, generation and every
other manager's entry stay exactly as they are. Without `--apply` it only plans.

1. Render the Deployment the next rollout applies, with the same arguments the deploy script uses.
   `IMAGE_TAG` is the tag the rollout will deploy; add the repository and digest pair only when the
   rollout deploys a digest.

   ```bash
   helm template "$RELEASE" backend/charts/llm-gateway \
     -f backend/charts/llm-gateway/prod_omi_llm_gateway_values.yaml \
     --set-string "image.tag=${IMAGE_TAG}" \
     --set-string "serviceAccount.annotations.iam\\.gke\\.io/gcp-service-account=${LLM_GATEWAY_GSA}" \
     --show-only templates/deployment.yaml > next-deployment.yaml
   ```

2. Plan. The tool prints the serving image, the image owner and the entry it would remove:

   ```bash
   python3 backend/scripts/handoff-llm-gateway-image-ownership.py --next-deployment next-deployment.yaml
   ```

   With `--next-deployment` the tool first proves that this exact manifest fails the ordinary Helm
   apply on the one expected conflict. It then sends the patch as a server-side dry-run and refuses
   unless the result matches the plan.

3. Apply the plan, under the release owner's authorization:

   ```bash
   python3 backend/scripts/handoff-llm-gateway-image-ownership.py --next-deployment next-deployment.yaml --apply
   ```

   The tool rereads the Deployment and exits with code 4 unless the cluster matches the plan, then
   proves the same manifest now passes the ordinary Helm apply. Exit code 3 means it refused and
   changed nothing.

4. Run the ordinary rollout that deploys `IMAGE_TAG`. It changes the image through Helm with no
   force and no ownership flag.

5. Read back the serving image and its owner:

   ```bash
   kubectl -n "$NS" get deployment "$RELEASE" --show-managed-fields -o json \
     | jq -r '.spec.template.spec.containers[0].image,
             (.metadata.managedFields[]
               | select(.fieldsV1["f:spec"]["f:template"]["f:spec"]["f:containers"]["k:{\"name\":\"llm-gateway\"}"]["f:image"])
               | "image owner: \(.manager)/\(.operation)")'
   ```

   The image is the one the rollout deployed and its owner is `helm/Apply`.

## What the tool refuses

The tool changes nothing and exits with code 3 when:

- the Deployment is not Helm-managed, or Helm has no server-side apply entry on it;
- the named manager owns nothing, or owns the image through more than one entry;
- the entry owns anything besides the image, for example container resources set by the same patch;
- the entry is not an `Update` of `apps/v1`, or targets a subresource;
- the server dry-run of the patch differs from the plan, for example because the Deployment changed
  between the read and the patch (the patch also tests the resource version).

A refusal for an entry that owns more than the image needs a person to decide field by field; do not
widen the tool to get past it.

## Never

- Do not pass `--force-conflicts` to Helm or `kubectl apply`. It takes every conflicting field in
  the release, not only the image, and hides the next ownership drift the same way.
- Do not clear `metadata.managedFields` or copy it between objects. Other managers' entries record
  what still owns the rest of the Deployment.
- Do not patch the image out of band again. The deploy now fails its preflight instead of stranding
  the rollout halfway.

## Reproduce the proof

`backend/scripts/proof-llm-gateway-ownership-handoff.sh` runs the real deploy script and handoff tool
against a kwokctl cluster on this machine: a real API server and controllers whose Nodes are
simulated. It asserts that a conflicting owner fails the deploy before any write, that the handoff
leaves the serving image and the other owners intact, that a different tag and a digest then roll
through ordinary Helm, and that an entry owning more than the image is refused. With `kwokctl`, Helm
4, `kubectl`, `jq` and `python3` on `PATH`, from the repository root:

```bash
bash backend/scripts/proof-llm-gateway-ownership-handoff.sh
```

The proof creates its own cluster, under a name unique to that run, and deletes it when it finishes.
`--keep` leaves the cluster and its kubeconfig in place to inspect a failure.

The proof never reads your kubeconfig. Before its first write it establishes, by reads only, that
the cluster is the one it just created, and refuses otherwise:

- `kwokctl` lists the cluster under that name.
- The kubeconfig in use is the one `kwokctl` wrote for it and names no other cluster.
- Its API server is on loopback and reports an upstream Kubernetes build.
- The cluster holds nothing: no Nodes, Pods or CRDs, and only the four default namespaces.

A remote cluster that a local port-forward or proxy serves on loopback is refused: its kubeconfig is
not the one `kwokctl` wrote for the run, and it is not empty.
