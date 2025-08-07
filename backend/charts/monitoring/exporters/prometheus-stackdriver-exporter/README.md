# Stackdriver Exporter

Prometheus exporter for Stackdriver, allowing for Google Cloud metrics.
You must have appropriate IAM permissions for this exporter to work.
If you are passing in an IAM key then you must have:

* monitoring.metricDescriptors.list
* monitoring.timeSeries.list

These are contained within `roles/monitoring.viewer`.
If you're using legacy access scopes, then you must have `https://www.googleapis.com/auth/monitoring.read`.

Learn more: <https://github.com/prometheus-community/stackdriver_exporter>

This chart creates a Stackdriver-Exporter deployment on a
[Kubernetes](http://kubernetes.io) cluster using the [Helm](https://helm.sh)
package manager.

## Prerequisites

* Kubernetes 1.8+ with Beta APIs enabled

## Usage

The chart is distributed as an [OCI Artifact](https://helm.sh/docs/topics/registries/) as well as via a traditional [Helm Repository](https://helm.sh/docs/topics/chart_repository/).

* OCI Artifact: `oci://ghcr.io/prometheus-community/charts/prometheus-stackdriver-exporter`
* Helm Repository: `https://prometheus-community.github.io/helm-charts` with chart `prometheus-stackdriver-exporter`

The installation instructions use the OCI registry. Refer to the [`helm repo`]([`helm repo`](https://helm.sh/docs/helm/helm_repo/)) command documentation for information on installing charts via the traditional repository.

### Install Chart

```console
# Helm 3
$ helm install [RELEASE_NAME] oci://ghcr.io/prometheus-community/charts/prometheus-stackdriver-exporter --set stackdriver.projectId=google-project-name

# Helm 2
$ helm install --name [RELEASE_NAME] oci://ghcr.io/prometheus-community/charts/prometheus-stackdriver-exporter --set stackdriver.projectId=google-project-name
```

The command deploys Stackdriver-Exporter on the Kubernetes cluster using the default configuration.

_See [configuration](#configuration) below._

_See [helm install](https://helm.sh/docs/helm/helm_install/) for command documentation._

### Uninstall Chart

```console
# Helm 3
$ helm uninstall [RELEASE_NAME]

# Helm 2
# helm delete --purge [RELEASE_NAME]
```

This removes all the Kubernetes components associated with the chart and deletes the release.

_See [helm uninstall](https://helm.sh/docs/helm/helm_uninstall/) for command documentation._

### Upgrading Chart

```console
# Helm 3 or 2
$ helm upgrade [RELEASE_NAME] [CHART] --install
```

_See [helm upgrade](https://helm.sh/docs/helm/helm_upgrade/) for command documentation._

#### Upgrading an existing Release to a new major version

A major chart version change (like v1.2.3 -> v2.0.0) indicates that there is an incompatible breaking change needing manual actions.

##### 3.x to 4.x

The Helm parameter `stackdriver.metrics.filters` is changed to support multiple values instead of a single value. If you are using this parameter, please adjust.

```console
stackdriver:
  metrics:
    filters:
      - filter-1
      - filter-2
```

##### 2.x to 3.x

Due to a change in deployment labels, **removal** of its deployment needs to done manually prior to upgrading:

```console
kubectl delete deployments.apps -l app=prometheus-stackdriver-exporter --cascade=orphan
```

If this is not done, when upgrading via helm (even with `helm upgrade --force`) an error will occur indicating that the deployment cannot be modified:

```console
invalid: spec.selector: Invalid value: v1.LabelSelector{MatchLabels:map[string]string{"app.kubernetes.io/instance":"example", "app.kubernetes.io/name":"prometheus-stackdriver-exporter"}, MatchExpressions:[]v1.LabelSelectorRequirement(nil)}: field is immutable
```

Since chart version 3.x, [Kubernetes recommended labels](https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/) have been **added**.

The following labels are now **removed** in all manifests (including labels used as selector for `Deployment` kind):

```yaml
...
metadata:
  labels:
    app: prometheus-stackdriver-exporter
    chart: prometheus-stackdriver-exporter-2.X.X
    heritage: Helm
    release: example
...
spec:
  ...
  selector:
    matchLabels:
      app: prometheus-stackdriver-exporter
      release: example
...
```

If you use your own custom [ServiceMonitor](https://github.com/prometheus-operator/prometheus-operator/blob/main/Documentation/api-reference/api.md#servicemonitor) or [PodMonitor](https://github.com/prometheus-operator/prometheus-operator/blob/main/Documentation/api-reference/api.md#podmonitor), please ensure to upgrade their `selector` fields accordingly to the new labels.

##### 1.x to 2.x

Since chart version 2.0.0, the exporter is configured via flags/arguments instead of environment variables due to a [breaking change in the exporter](https://github.com/prometheus-community/stackdriver_exporter/pull/142).

If you already use `.Values.extraArgs` you might want to check for conflicting command arguments.

## Configuration

See [Customizing the Chart Before Installing](https://helm.sh/docs/intro/using_helm/#customizing-the-chart-before-installing).
To see all configurable options with detailed comments, visit the chart's [values.yaml](./values.yaml), or run these configuration commands:

```console
# Helm 2
$ helm inspect values oci://ghcr.io/prometheus-community/charts/prometheus-stackdriver-exporter

# Helm 3
$ helm show values oci://ghcr.io/prometheus-community/charts/prometheus-stackdriver-exporter
```

> **Tip**: You can use the default [values.yaml](values.yaml), as long as you provide a value for stackdriver.projectId

## Google Storage Metrics

In order to get metrics for GCS you need to ensure the metrics interval is >
24h.  You can read more information about this in [this bug
report](https://github.com/frodenas/stackdriver_exporter/issues/14).

The easiest way to do this is to create two separate exporters with different
prefixes and intervals, to ensure you gather all appropriate metrics.
