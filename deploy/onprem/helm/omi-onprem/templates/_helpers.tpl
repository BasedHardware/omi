{{/* Common labels applied to every object. */}}
{{- define "omi-onprem.labels" -}}
app.kubernetes.io/part-of: omi-onprem
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{/*
Stable DNS name of the single replica-set member. StatefulSet "mongo" + headless Service "mongo"
give pod mongo-0 a stable FQDN; the RS is initiated with THIS host so it survives pod restarts and
the backend/init-job resolve the same member (§6.1).
*/}}
{{- define "omi-onprem.mongoHost" -}}
mongo-0.mongo.{{ .Release.Namespace }}.svc.cluster.local
{{- end -}}
