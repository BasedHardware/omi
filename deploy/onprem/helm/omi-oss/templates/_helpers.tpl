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
Resolve one of OUR built images (backend + in-cluster inference). Prefix `imageRegistry` when set:
empty  -> bare name (Kind: `kind load` + imagePullPolicy Never, no registry);
<host> -> <host>/<repo> (k0s: the node pulls from the local registry). Call: (dict "root" $ "repo" "omi-oss-x:latest").
*/}}
{{- define "omi-oss.image" -}}
{{- $reg := .root.Values.imageRegistry | default "" | trimSuffix "/" -}}
{{- if $reg }}{{ $reg }}/{{ .repo }}{{ else }}{{ .repo }}{{ end -}}
{{- end -}}

{{/*
OIDC issuer host: the explicit auth.hostname, else derived from the pinned LoadBalancer IP (so a single
value, ingress.loadBalancerIP, fixes the issuer + TLS SAN without repeating the address).
*/}}
{{- define "omi-oss.authHostname" -}}
{{- .Values.auth.hostname | default (printf "https://%s" .Values.ingress.loadBalancerIP) -}}
{{- end -}}
