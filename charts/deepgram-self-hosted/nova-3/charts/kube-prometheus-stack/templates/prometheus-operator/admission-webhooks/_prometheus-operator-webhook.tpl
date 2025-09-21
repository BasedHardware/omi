{{/* Generate basic labels for prometheus-operator-webhook */}}
{{- define "kube-prometheus-stack.prometheus-operator-webhook.labels" }}
{{- include "kube-prometheus-stack.labels" . }}
app.kubernetes.io/name: {{ template "kube-prometheus-stack.name" . }}-prometheus-operator
app.kubernetes.io/component: prometheus-operator-webhook
{{- end }}
