{{/* Common labels applied to every object. */}}
{{- define "omi-oss.labels" -}}
app.kubernetes.io/part-of: omi-oss
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{/*
Stable DNS name of the single replica-set member. StatefulSet "mongo" + headless Service "mongo"
give pod mongo-0 a stable FQDN; the RS is initiated with THIS host so it survives pod restarts and
the backend/init-job resolve the same member (§6.1).
*/}}
{{- define "omi-oss.mongoHost" -}}
mongo-0.mongo.{{ .Release.Namespace }}.svc.cluster.local
{{- end -}}

{{/*
Resolve one of OUR built images (backend + in-cluster inference) as <registry>/<repository>:<tag>.

The TAG defaults to .Chart.AppVersion, which is this chart's projection of the compose-side release
(deploy/onprem/omi.oss.release.env, ADR-0054 — a CI check fails if the two drift). An overlay may pin
`tag` explicitly; the dev overlay uses `latest`, the alias the build produces next to the release for
`kind load`. Prod/k0s must NOT use `latest` (checked).

`imageRegistry` is prefixed when set: empty -> bare name (Kind: `kind load` + imagePullPolicy Never,
no registry); <host> -> <host>/<repository> (k0s: the node pulls from the local registry).
Call: (dict "root" $ "image" .Values.backend.image).
*/}}
{{- define "omi-oss.image" -}}
{{- $reg := .root.Values.imageRegistry | default "" | trimSuffix "/" -}}
{{- $repo := required "image.repository is required" .image.repository -}}
{{- $tag := .image.tag | default .root.Chart.AppVersion -}}
{{- if $reg }}{{ $reg }}/{{ $repo }}:{{ $tag }}{{ else }}{{ $repo }}:{{ $tag }}{{ end -}}
{{- end -}}

{{/*
OIDC issuer host: the explicit auth.hostname, else derived from the pinned LoadBalancer IP (so a single
value, ingress.loadBalancerIP, fixes the issuer + TLS SAN without repeating the address).
*/}}
{{- define "omi-oss.authHostname" -}}
{{- .Values.auth.hostname | default (printf "https://%s" .Values.ingress.loadBalancerIP) -}}
{{- end -}}

{{/*
Public base URL of THIS deployment's API, for identities we publish to clients (today: the MCP
protected-resource document). Same derivation as authHostname — the HTTPRoute is hostname-agnostic and
the API answers on the pinned LoadBalancer IP — but a separate value, because an operator may terminate
auth and API on different names.
*/}}
{{- define "omi-oss.apiHostname" -}}
{{- if .Values.api.hostname -}}
{{- .Values.api.hostname -}}
{{- else if .Values.ingress.loadBalancerIP -}}
{{- printf "https://%s" .Values.ingress.loadBalancerIP -}}
{{- end -}}
{{- end -}}
