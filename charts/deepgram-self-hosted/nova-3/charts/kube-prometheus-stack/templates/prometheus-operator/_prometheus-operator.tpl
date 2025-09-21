{{/* Generate basic labels for prometheus-operator */}}
{{- define "kube-prometheus-stack.prometheus-operator.labels" }}
{{- include "kube-prometheus-stack.labels" . }}
app: {{ template "kube-prometheus-stack.name" . }}-operator
app.kubernetes.io/name: {{ template "kube-prometheus-stack.name" . }}-prometheus-operator
app.kubernetes.io/component: prometheus-operator
{{- end }}
