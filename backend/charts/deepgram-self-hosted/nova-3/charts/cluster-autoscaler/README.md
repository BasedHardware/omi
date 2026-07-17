# cluster-autoscaler

Scales Kubernetes worker nodes within autoscaling groups.

## TL;DR

```console
$ helm repo add autoscaler https://kubernetes.github.io/autoscaler

# Method 1 - Using Autodiscovery
$ helm install my-release autoscaler/cluster-autoscaler \
    --set 'autoDiscovery.clusterName'=<CLUSTER NAME>

# Method 2 - Specifying groups manually
$ helm install my-release autoscaler/cluster-autoscaler \
    --set "autoscalingGroups[0].name=your-asg-name" \
    --set "autoscalingGroups[0].maxSize=10" \
    --set "autoscalingGroups[0].minSize=1"
```

## Introduction

This chart bootstraps a cluster-autoscaler deployment on a [Kubernetes](http://kubernetes.io) cluster using the [Helm](https://helm.sh) package manager.

## Prerequisites

- Helm 3+
- Kubernetes 1.8+
  - [Older versions](https://github.com/kubernetes/autoscaler/tree/master/cluster-autoscaler#releases) may work by overriding the `image`. Cluster autoscaler internally simulates the scheduler and bugs between mismatched versions may be subtle.
- Azure AKS specific Prerequisites:
  - Kubernetes 1.10+ with RBAC-enabled.

## Previous Helm Chart

The previous `cluster-autoscaler` Helm chart hosted at [helm/charts](https://github.com/helm/charts) has been moved to this repository in accordance with the [Deprecation timeline](https://github.com/helm/charts#deprecation-timeline). Note that a few things have changed between this version and the old version:

- This repository **only** supports Helm chart installations using Helm 3+ since the `apiVersion` on the charts has been marked as `v2`.
- Previous versions of the Helm chart have not been migrated

## Migration from 1.X to 9.X+ versions of this Chart

**TL;DR:**
You should choose to use versions >=9.0.0 of the `cluster-autoscaler` chart published from this repository; previous versions, and the `cluster-autoscaler-chart` with versioning 1.X.X published from this repository are deprecated.

<details>
  <summary>Previous versions of this chart - further details</summary>
On initial migration of this chart from the `helm/charts` repository this chart was renamed from `cluster-autoscaler` to `cluster-autoscaler-chart` due to technical limitations. This affected all `1.X` releases of the chart, version 2.0.0 of this chart exists only to mark the [`cluster-autoscaler-chart` chart](https://artifacthub.io/packages/helm/cluster-autoscaler/cluster-autoscaler-chart) as deprecated.

Releases of the chart from `9.0.0` onwards return the naming of the chart to `cluster-autoscaler` and return to following the versioning established by the chart's previous location at .

To migrate from a 1.X release of the chart to a `9.0.0` or later release, you should first uninstall your `1.X` install of the `cluster-autoscaler-chart` chart, before performing the installation of the new `cluster-autoscaler` chart.
</details>

## Migration from 9.0 to 9.1

Starting from `9.1.0` the `envFromConfigMap` value is expected to contain the name of a ConfigMap that is used as ref for `envFrom`, similar to `envFromSecret`. If you want to keep the previous behaviour of `envFromConfigMap` you must rename it to `extraEnvConfigMaps`.

## Installing the Chart

**By default, no deployment is created and nothing will autoscale**.

You must provide some minimal configuration, either to specify instance groups or enable auto-discovery. It is not recommended to do both.

Either:

- Set `autoDiscovery.clusterName` and provide additional autodiscovery options if necessary **or**
- Set static node group configurations for one or more node groups (using `autoscalingGroups` or `autoscalingGroupsnamePrefix`).

To create a valid configuration, follow instructions for your cloud provider:

- [AWS](#aws---using-auto-discovery-of-tagged-instance-groups)
- [GCE](#gce)
- [Azure](#azure)
- [OpenStack Magnum](#openstack-magnum)
- [Cluster API](#cluster-api)
- [Exoscale](#exoscale)
- [Hetzner Cloud](#hetzner-cloud)
- [Civo](#civo)

### Templating the autoDiscovery.clusterName

The cluster name can be templated in the `autoDiscovery.clusterName` variable. This is useful when the cluster name is dynamically generated based on other values coming from external systems like Argo CD or Flux. This also allows you to use global Helm values to set the cluster name, e.g., `autoDiscovery.clusterName={{ .Values.global.clusterName }}`, so that you don't need to set it in more than 1 location in the values file.

### AWS - Using auto-discovery of tagged instance groups

Auto-discovery finds ASGs tags as below and automatically manages them based on the min and max size specified in the ASG. `cloudProvider=aws` only.

- Tag the ASGs with keys to match `.Values.autoDiscovery.tags`, by default: `k8s.io/cluster-autoscaler/enabled` and `k8s.io/cluster-autoscaler/<YOUR CLUSTER NAME>`
- Verify the [IAM Permissions](#aws---iam)
- Set `autoDiscovery.clusterName=<YOUR CLUSTER NAME>`
- Set `awsRegion=<YOUR AWS REGION>`
- Set (option) `awsAccessKeyID=<YOUR AWS KEY ID>` and `awsSecretAccessKey=<YOUR AWS SECRET KEY>` if you want to [use AWS credentials directly instead of an instance role](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/aws/README.md#using-aws-credentials)

```console
$ helm install my-release autoscaler/cluster-autoscaler \
    --set autoDiscovery.clusterName=<CLUSTER NAME> \
    --set awsRegion=<YOUR AWS REGION>
```

Alternatively with your own AWS credentials

```console
$ helm install my-release autoscaler/cluster-autoscaler \
    --set autoDiscovery.clusterName=<CLUSTER NAME> \
    --set awsRegion=<YOUR AWS REGION> \
    --set awsAccessKeyID=<YOUR AWS KEY ID> \
    --set awsSecretAccessKey=<YOUR AWS SECRET KEY>
```

#### Specifying groups manually

Without autodiscovery, specify an array of elements each containing ASG name, min size, max size. The sizes specified here will be applied to the ASG, assuming IAM permissions are correctly configured.

- Verify the [IAM Permissions](#aws---iam)
- Either provide a yaml file setting `autoscalingGroups` (see values.yaml) or use `--set` e.g.:

```console
$ helm install my-release autoscaler/cluster-autoscaler \
    --set "autoscalingGroups[0].name=your-asg-name" \
    --set "autoscalingGroups[0].maxSize=10" \
    --set "autoscalingGroups[0].minSize=1"
```

#### Auto-discovery

For auto-discovery of instances to work, they must be tagged with the keys in `.Values.autoDiscovery.tags`, which by default are `k8s.io/cluster-autoscaler/enabled` and `k8s.io/cluster-autoscaler/<ClusterName>`.

The value of the tag does not matter, only the key.

An example kops spec excerpt:

```yaml
apiVersion: kops/v1alpha2
kind: Cluster
metadata:
  name: my.cluster.internal
spec:
  additionalPolicies:
    node: |
      [
        {"Effect":"Allow","Action":["autoscaling:DescribeAutoScalingGroups","autoscaling:DescribeAutoScalingInstances","autoscaling:DescribeLaunchConfigurations","autoscaling:DescribeTags","autoscaling:SetDesiredCapacity","autoscaling:TerminateInstanceInAutoScalingGroup"],"Resource":"*"}
      ]
      ...
---
apiVersion: kops/v1alpha2
kind: InstanceGroup
metadata:
  labels:
    kops.k8s.io/cluster: my.cluster.internal
  name: my-instances
spec:
  cloudLabels:
    k8s.io/cluster-autoscaler/enabled: ""
    k8s.io/cluster-autoscaler/my.cluster.internal: ""
  image: kops.io/k8s-1.8-debian-jessie-amd64-hvm-ebs-2018-01-14
  machineType: r4.large
  maxSize: 4
  minSize: 0
```

In this example you would need to `--set autoDiscovery.clusterName=my.cluster.internal` when installing.

It is not recommended to try to mix this with setting `autoscalingGroups`.

See [autoscaler AWS documentation](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/aws/README.md#auto-discovery-setup) for a more discussion of the setup.

### GCE

The following parameters are required:

- `autoDiscovery.clusterName=any-name`
- `cloud-provider=gce`
- `autoscalingGroupsnamePrefix[0].name=your-ig-prefix,autoscalingGroupsnamePrefix[0].maxSize=10,autoscalingGroupsnamePrefix[0].minSize=1`

To use Managed Instance Group (MIG) auto-discovery, provide a YAML file setting `autoscalingGroupsnamePrefix` (see values.yaml) or use `--set` when installing the Chart - e.g.

```console
$ helm install my-release autoscaler/cluster-autoscaler \
    --set "autoscalingGroupsnamePrefix[0].name=your-ig-prefix,autoscalingGroupsnamePrefix[0].maxSize=10,autoscalingGroupsnamePrefix[0].minSize=1" \
    --set autoDiscovery.clusterName=<CLUSTER NAME> \
    --set cloudProvider=gce
```

Note that `your-ig-prefix` should be a _prefix_ matching one or more MIGs, and _not_ the full name of the MIG. For example, to match multiple instance groups - `k8s-node-group-a-standard`, `k8s-node-group-b-gpu`, you would use a prefix of `k8s-node-group-`.

Prefixes will be rendered using `tpl` function so you can use any value of your choice if that's a valid prefix. For instance (ignore escaping characters): `gke-{{ .Values.autoDiscovery.clusterName }}`

In the event you want to explicitly specify MIGs instead of using auto-discovery, set members of the `autoscalingGroups` array directly - e.g.

```
# where 'n' is the index, starting at 0
--set autoscalingGroups[n].name=https://content.googleapis.com/compute/v1/projects/$PROJECTID/zones/$ZONENAME/instanceGroups/$FULL-MIG-NAME,autoscalingGroups[n].maxSize=$MAXSIZE,autoscalingGroups[n].minSize=$MINSIZE
```

### Azure

The following parameters are required:

- `cloudProvider=azure`
- `autoscalingGroups[0].name=your-vmss,autoscalingGroups[0].maxSize=10,autoscalingGroups[0].minSize=1`
- `azureClientID: "your-service-principal-app-id"`
- `azureClientSecret: "your-service-principal-client-secret"`
- `azureSubscriptionID: "your-azure-subscription-id"`
- `azureTenantID: "your-azure-tenant-id"`
- `azureResourceGroup: "your-aks-cluster-resource-group-name"`
- `azureVMType: "vmss"`

### OpenStack Magnum

`cloudProvider: magnum` must be set, and then one of

- `magnumClusterName=<cluster name or ID>` and `autoscalingGroups` with the names of node groups and min/max node counts
- or `autoDiscovery.clusterName=<cluster name or ID>` with one or more `autoDiscovery.roles`.

Additionally, `cloudConfigPath: "/etc/kubernetes/cloud-config"` must be set as this should be the location of the cloud-config file on the host.

Example values files can be found [here](../../cluster-autoscaler/cloudprovider/magnum/examples).

Install the chart with

```console
$ helm install my-release autoscaler/cluster-autoscaler -f myvalues.yaml
```

### Cluster-API

`cloudProvider: clusterapi` must be set, and then one or more of

- `autoDiscovery.clusterName`
- or `autoDiscovery.namespace`
- or `autoDiscovery.labels`

See [here](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/clusterapi/README.md#configuring-node-group-auto-discovery) for more details.

Additional config parameters available, see the `values.yaml` for more details

- `clusterAPIMode`
- `clusterAPIKubeconfigSecret`
- `clusterAPIWorkloadKubeconfigPath`
- `clusterAPICloudConfigPath`

### Exoscale

Create a `values.yaml` file with the following content:
```yaml
cloudProvider: exoscale
autoDiscovery:
  clusterName: cluster.local # this value is not used, but must be set
```

Optionally, you may specify the minimum and maximum size of a particular nodepool by adding the following to the `values.yaml` file:
```yaml
autoscalingGroups:
  - name: your-nodepool-name
    maxSize: 10
    minSize: 1
```

Create an Exoscale API key with appropriate permissions as described in [cluster-autoscaler/cloudprovider/exoscale/README.md](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/exoscale/README.md).
A secret of name `<release-name>-exoscale-cluster-autoscaler` needs to be created, containing the api key and secret, as well as the zone.

```console
$ kubectl create secret generic my-release-exoscale-cluster-autoscaler \
    --from-literal=api-key="EXOxxxxxxxxxxxxxxxxxxxxxxxx" \
    --from-literal=api-secret="xxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" --from-literal=api-zone="ch-gva-2"
```

After creating the secret, the chart may be installed:

```console
$ helm install my-release autoscaler/cluster-autoscaler -f values.yaml
```

Read [cluster-autoscaler/cloudprovider/exoscale/README.md](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/exoscale/README.md) for further information on the setup without helm.

### Hetzner Cloud

The following parameters are required:

- `cloudProvider=hetzner`
- `extraEnv.HCLOUD_TOKEN=...`
- `autoscalingGroups=...`

Each autoscaling group requires an additional `instanceType` and `region` key to be set.

Read [cluster-autoscaler/cloudprovider/hetzner/README.md](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/hetzner/README.md) for further information on the setup without helm.

### Civo

The following parameters are required:

- `cloudProvider=civo`
- `autoscalingGroups=...`

When installing the helm chart to the namespace `kube-system`, you can set `secretKeyRefNameOverride` to `civo-api-access`.
Otherwise specify the following parameters:

- `civoApiUrl=https://api.civo.com`
- `civoApiKey=...`
- `civoClusterID=...`
- `civoRegion=...`

Read [cluster-autoscaler/cloudprovider/civo/README.md](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/civo/README.md) for further information on the setup without helm.

## Uninstalling the Chart

To uninstall `my-release`:

```console
$ helm uninstall my-release
```

The command removes all the Kubernetes components associated with the chart and deletes the release.

> **Tip**: List all releases using `helm list` or start clean with `helm uninstall my-release`

## Additional Configuration

### AWS - IAM

The worker running the cluster autoscaler will need access to certain resources and actions depending on the version you run and your configuration of it.

For the up-to-date IAM permissions required, please see the [cluster autoscaler's AWS Cloudprovider Readme](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/aws/README.md#iam-policy) and switch to the tag of the cluster autoscaler image you are using.

### AWS - IAM Roles for Service Accounts (IRSA)

For Kubernetes clusters that use Amazon EKS, the service account can be configured with an IAM role using [IAM Roles for Service Accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) to avoid needing to grant access to the worker nodes for AWS resources.

In order to accomplish this, you will first need to create a new IAM role with the above mentions policies.  Take care in [configuring the trust relationship](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts-technical-overview.html#iam-role-configuration) to restrict access just to the service account used by cluster autoscaler.

Once you have the IAM role configured, you would then need to `--set rbac.serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=arn:aws:iam::123456789012:role/MyRoleName` when installing. Alternatively, you can embed templates in values (ignore escaping characters):

```yaml
rbac:
  serviceAccount:
    annotations:
      eks.amazonaws.com/role-arn: "{{ .Values.aws.myroleARN }}"
```

### Azure - Using azure workload identity

You can use the project [Azure workload identity](https://github.com/Azure/azure-workload-identity), to automatically configure the correct setup for your pods to used federated identity with Azure.

You can also set the correct settings yourself instead of relying on this project.

For example the following configuration will configure the Autoscaler to use your federated identity:

```yaml
azureUseWorkloadIdentityExtension: true
extraEnv:
  AZURE_CLIENT_ID: USER ASSIGNED IDENTITY CLIENT ID
  AZURE_TENANT_ID: USER ASSIGNED IDENTITY TENANT ID
  AZURE_FEDERATED_TOKEN_FILE: /var/run/secrets/tokens/azure-identity-token
  AZURE_AUTHORITY_HOST: https://login.microsoftonline.com/
extraVolumes:
- name: azure-identity-token
  projected:
    defaultMode: 420
    sources:
    - serviceAccountToken:
        audience: api://AzureADTokenExchange
        expirationSeconds: 3600
        path: azure-identity-token
extraVolumeMounts:
- mountPath: /var/run/secrets/tokens
  name: azure-identity-token
  readOnly: true
```

### Custom arguments

You can use the `customArgs` value to give any argument to cluster autoscaler command.

Typical use case is to give an environment variable as an argument which will be interpolated at execution time.

This is helpful when you need to inject values from configmap or secret.

## Troubleshooting

The chart will succeed even if the container arguments are incorrect. A few minutes after starting `kubectl logs -l "app=aws-cluster-autoscaler" --tail=50` should loop through something like

```
polling_autoscaler.go:111] Poll finished
static_autoscaler.go:97] Starting main loop
utils.go:435] No pod using affinity / antiaffinity found in cluster, disabling affinity predicate for this loop
static_autoscaler.go:230] Filtering out schedulables
```

If not, find a pod that the deployment created and `describe` it, paying close attention to the arguments under `Command`. e.g.:

```
Containers:
  cluster-autoscaler:
    Command:
      ./cluster-autoscaler
      --cloud-provider=aws
# if specifying ASGs manually
      --nodes=1:10:your-scaling-group-name
# if using autodiscovery
      --node-group-auto-discovery=asg:tag=k8s.io/cluster-autoscaler/enabled,k8s.io/cluster-autoscaler/<ClusterName>
      --v=4
```

### PodSecurityPolicy

Though enough for the majority of installations, the default PodSecurityPolicy _could_ be too restrictive depending on the specifics of your release. Please make sure to check that the template fits with any customizations made or disable it by setting `rbac.pspEnabled` to `false`.

### VerticalPodAutoscaler

The CA Helm Chart can install a [`VerticalPodAutoscaler`](https://github.com/kubernetes/autoscaler/blob/master/vertical-pod-autoscaler/README.md) object from Chart version `9.27.0`
onwards for the Cluster Autoscaler Deployment to scale the CA as appropriate, but for that, we
need to install the VPA to the cluster separately. A VPA can help minimize wasted resources
when usage spikes periodically or remediate containers that are being OOMKilled.

The following example snippet can be used to install VPA that allows scaling down from the default recommendations of the deployment template:

```yaml
vpa:
  enabled: true
  containerPolicy:
    minAllowed:
      cpu: 20m
      memory: 50Mi
```

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| additionalLabels | object | `{}` | Labels to add to each object of the chart. |
| affinity | object | `{}` | Affinity for pod assignment |
| autoDiscovery.clusterName | string | `nil` | Enable autodiscovery for `cloudProvider=aws`, for groups matching `autoDiscovery.tags`. autoDiscovery.clusterName -- Enable autodiscovery for `cloudProvider=azure`, using tags defined in https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/azure/README.md#auto-discovery-setup. Enable autodiscovery for `cloudProvider=clusterapi`, for groups matching `autoDiscovery.labels`. Enable autodiscovery for `cloudProvider=gce`, but no MIG tagging required. Enable autodiscovery for `cloudProvider=magnum`, for groups matching `autoDiscovery.roles`. |
| autoDiscovery.labels | list | `[]` | Cluster-API labels to match  https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/clusterapi/README.md#configuring-node-group-auto-discovery |
| autoDiscovery.namespace | string | `nil` | Enable autodiscovery via cluster namespace for for `cloudProvider=clusterapi` |
| autoDiscovery.roles | list | `["worker"]` | Magnum node group roles to match. |
| autoDiscovery.tags | list | `["k8s.io/cluster-autoscaler/enabled","k8s.io/cluster-autoscaler/{{ .Values.autoDiscovery.clusterName }}"]` | ASG tags to match, run through `tpl`. |
| autoscalingGroups | list | `[]` | For AWS, Azure AKS, Exoscale or Magnum. At least one element is required if not using `autoDiscovery`. For example: <pre> - name: asg1<br />   maxSize: 2<br />   minSize: 1 </pre> For Hetzner Cloud, the `instanceType` and `region` keys are also required. <pre> - name: mypool<br />   maxSize: 2<br />   minSize: 1<br />   instanceType: CPX21<br />   region: FSN1 </pre> |
| autoscalingGroupsnamePrefix | list | `[]` | For GCE. At least one element is required if not using `autoDiscovery`. For example: <pre> - name: ig01<br />   maxSize: 10<br />   minSize: 0 </pre> |
| awsAccessKeyID | string | `""` | AWS access key ID ([if AWS user keys used](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/aws/README.md#using-aws-credentials)) |
| awsRegion | string | `""` | AWS region (required if `cloudProvider=aws`) |
| awsSecretAccessKey | string | `""` | AWS access secret key ([if AWS user keys used](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/aws/README.md#using-aws-credentials)) |
| azureClientID | string | `""` | Service Principal ClientID with contributor permission to Cluster and Node ResourceGroup. Required if `cloudProvider=azure` |
| azureClientSecret | string | `""` | Service Principal ClientSecret with contributor permission to Cluster and Node ResourceGroup. Required if `cloudProvider=azure` |
| azureEnableForceDelete | bool | `false` | Whether to force delete VMs or VMSS instances when scaling down. |
| azureResourceGroup | string | `""` | Azure resource group that the cluster is located. Required if `cloudProvider=azure` |
| azureSubscriptionID | string | `""` | Azure subscription where the resources are located. Required if `cloudProvider=azure` |
| azureTenantID | string | `""` | Azure tenant where the resources are located. Required if `cloudProvider=azure` |
| azureUseManagedIdentityExtension | bool | `false` | Whether to use Azure's managed identity extension for credentials. If using MSI, ensure subscription ID, resource group, and azure AKS cluster name are set. You can only use one authentication method at a time, either azureUseWorkloadIdentityExtension or azureUseManagedIdentityExtension should be set. |
| azureUseWorkloadIdentityExtension | bool | `false` | Whether to use Azure's workload identity extension for credentials. See the project here: https://github.com/Azure/azure-workload-identity for more details. You can only use one authentication method at a time, either azureUseWorkloadIdentityExtension or azureUseManagedIdentityExtension should be set. |
| azureUserAssignedIdentityID | string | `""` | When vmss has multiple user assigned identity assigned, azureUserAssignedIdentityID specifies which identity to be used |
| azureVMType | string | `"vmss"` | Azure VM type. |
| civoApiKey | string | `""` | API key for the Civo API. Required if `cloudProvider=civo` |
| civoApiUrl | string | `"https://api.civo.com"` | URL for the Civo API. Required if `cloudProvider=civo` |
| civoClusterID | string | `""` | Cluster ID for the Civo cluster. Required if `cloudProvider=civo` |
| civoRegion | string | `""` | Region for the Civo cluster. Required if `cloudProvider=civo` |
| cloudConfigPath | string | `""` | Configuration file for cloud provider. |
| cloudProvider | string | `"aws"` | The cloud provider where the autoscaler runs. Currently only `gce`, `aws`, `azure`, `magnum`, `clusterapi`, `civo` and `coreweave` are supported. `aws` supported for AWS. `gce` for GCE. `azure` for Azure AKS. `magnum` for OpenStack Magnum, `clusterapi` for Cluster API. `civo` for Civo Cloud. `coreweave` for CoreWeave. |
| clusterAPICloudConfigPath | string | `"/etc/kubernetes/mgmt-kubeconfig"` | Path to kubeconfig for connecting to Cluster API Management Cluster, only used if `clusterAPIMode=kubeconfig-kubeconfig or incluster-kubeconfig` |
| clusterAPIConfigMapsNamespace | string | `""` | Namespace on the workload cluster to store Leader election and status configmaps |
| clusterAPIKubeconfigSecret | string | `""` | Secret containing kubeconfig for connecting to Cluster API managed workloadcluster Required if `cloudProvider=clusterapi` and `clusterAPIMode=kubeconfig-kubeconfig,kubeconfig-incluster or incluster-kubeconfig` |
| clusterAPIMode | string | `"incluster-incluster"` | Cluster API mode, see https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/cloudprovider/clusterapi/README.md#connecting-cluster-autoscaler-to-cluster-api-management-and-workload-clusters Syntax: workloadClusterMode-ManagementClusterMode for `kubeconfig-kubeconfig`, `incluster-kubeconfig` and `single-kubeconfig` you always must mount the external kubeconfig using either `extraVolumeSecrets` or `extraMounts` and `extraVolumes` if you dont set `clusterAPIKubeconfigSecret`and thus use an in-cluster config or want to use a non capi generated kubeconfig you must do so for the workload kubeconfig as well |
| clusterAPIWorkloadKubeconfigPath | string | `"/etc/kubernetes/value"` | Path to kubeconfig for connecting to Cluster API managed workloadcluster, only used if `clusterAPIMode=kubeconfig-kubeconfig or kubeconfig-incluster` |
| containerSecurityContext | object | `{}` | [Security context for container](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/) |
| customArgs | list | `[]` | Additional custom container arguments. Refer to https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/FAQ.md#what-are-the-parameters-to-ca for the full list of cluster autoscaler parameters and their default values. List of arguments as strings. |
| deployment.annotations | object | `{}` | Annotations to add to the Deployment object. |
| dnsConfig | object | `{}` | [Pod's DNS Config](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/#pod-dns-config) |
| dnsPolicy | string | `"ClusterFirst"` | Defaults to `ClusterFirst`. Valid values are: `ClusterFirstWithHostNet`, `ClusterFirst`, `Default` or `None`. If autoscaler does not depend on cluster DNS, recommended to set this to `Default`. |
| envFromConfigMap | string | `""` | ConfigMap name to use as envFrom. |
| envFromSecret | string | `""` | Secret name to use as envFrom. |
| expanderPriorities | object | `{}` | The expanderPriorities is used if `extraArgs.expander` contains `priority` and expanderPriorities is also set with the priorities. If `extraArgs.expander` contains `priority`, then expanderPriorities is used to define cluster-autoscaler-priority-expander priorities. See: https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/expander/priority/readme.md |
| extraArgs | object | `{"logtostderr":true,"stderrthreshold":"info","v":4}` | Additional container arguments. Refer to https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/FAQ.md#what-are-the-parameters-to-ca for the full list of cluster autoscaler parameters and their default values. Everything after the first _ will be ignored allowing the use of multi-string arguments. |
| extraEnv | object | `{}` | Additional container environment variables. |
| extraEnvConfigMaps | object | `{}` | Additional container environment variables from ConfigMaps. |
| extraEnvSecrets | object | `{}` | Additional container environment variables from Secrets. |
| extraObjects | list | `[]` | Extra K8s manifests to deploy |
| extraVolumeMounts | list | `[]` | Additional volumes to mount. |
| extraVolumeSecrets | object | `{}` | Additional volumes to mount from Secrets. |
| extraVolumes | list | `[]` | Additional volumes. |
| fullnameOverride | string | `""` | String to fully override `cluster-autoscaler.fullname` template. |
| hostNetwork | bool | `false` | Whether to expose network interfaces of the host machine to pods. |
| image.pullPolicy | string | `"IfNotPresent"` | Image pull policy |
| image.pullSecrets | list | `[]` | Image pull secrets |
| image.repository | string | `"registry.k8s.io/autoscaling/cluster-autoscaler"` | Image repository |
| image.tag | string | `"v1.34.1"` | Image tag |
| initContainers | list | `[]` | Any additional init containers. |
| kubeTargetVersionOverride | string | `""` | Allow overriding the `.Capabilities.KubeVersion.GitVersion` check. Useful for `helm template` commands. |
| kwokConfigMapName | string | `"kwok-provider-config"` | configmap for configuring kwok provider |
| magnumCABundlePath | string | `"/etc/kubernetes/ca-bundle.crt"` | Path to the host's CA bundle, from `ca-file` in the cloud-config file. |
| magnumClusterName | string | `""` | Cluster name or ID in Magnum. Required if `cloudProvider=magnum` and not setting `autoDiscovery.clusterName`. |
| nameOverride | string | `""` | String to partially override `cluster-autoscaler.fullname` template (will maintain the release name) |
| nodeSelector | object | `{}` | Node labels for pod assignment. Ref: https://kubernetes.io/docs/user-guide/node-selection/. |
| podAnnotations | object | `{}` | Annotations to add to each pod. |
| podDisruptionBudget | object | `{"maxUnavailable":1}` | Pod disruption budget. |
| podLabels | object | `{}` | Labels to add to each pod. |
| priorityClassName | string | `"system-cluster-critical"` | priorityClassName |
| priorityConfigMapAnnotations | object | `{}` | Annotations to add to `cluster-autoscaler-priority-expander` ConfigMap. |
| prometheusRule.additionalLabels | object | `{}` | Additional labels to be set in metadata. |
| prometheusRule.enabled | bool | `false` | If true, creates a Prometheus Operator PrometheusRule. |
| prometheusRule.interval | string | `nil` | How often rules in the group are evaluated (falls back to `global.evaluation_interval` if not set). |
| prometheusRule.namespace | string | `"monitoring"` | Namespace which Prometheus is running in. |
| prometheusRule.rules | list | `[]` | Rules spec template (see https://github.com/prometheus-operator/prometheus-operator/blob/master/Documentation/api.md#rule). |
| rbac.additionalRules | list | `[]` | Additional rules for role/clusterrole |
| rbac.clusterScoped | bool | `true` | if set to false will only provision RBAC to alter resources in the current namespace. Most useful for Cluster-API |
| rbac.create | bool | `true` | If `true`, create and use RBAC resources. |
| rbac.pspEnabled | bool | `false` | If `true`, creates and uses RBAC resources required in the cluster with [Pod Security Policies](https://kubernetes.io/docs/concepts/policy/pod-security-policy/) enabled. Must be used with `rbac.create` set to `true`. |
| rbac.serviceAccount.annotations | object | `{}` | Additional Service Account annotations. |
| rbac.serviceAccount.automountServiceAccountToken | bool | `true` | Automount API credentials for a Service Account. |
| rbac.serviceAccount.create | bool | `true` | If `true` and `rbac.create` is also true, a Service Account will be created. |
| rbac.serviceAccount.name | string | `""` | The name of the ServiceAccount to use. If not set and create is `true`, a name is generated using the fullname template. |
| replicaCount | int | `1` | Desired number of pods |
| resources | object | `{}` | Pod resource requests and limits. |
| revisionHistoryLimit | int | `10` | The number of revisions to keep. |
| secretKeyRefNameOverride | string | `""` | Overrides the name of the Secret to use when loading the secretKeyRef for AWS, Azure and Civo env variables |
| securityContext | object | `{}` | [Security context for pod](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/) |
| service.annotations | object | `{}` | Annotations to add to service |
| service.clusterIP | string | `""` | IP address to assign to service |
| service.create | bool | `true` | If `true`, a Service will be created. |
| service.externalIPs | list | `[]` | List of IP addresses at which the service is available. Ref: https://kubernetes.io/docs/concepts/services-networking/service/#external-ips. |
| service.labels | object | `{}` | Labels to add to service |
| service.loadBalancerIP | string | `""` | IP address to assign to load balancer (if supported). |
| service.loadBalancerSourceRanges | list | `[]` | List of IP CIDRs allowed access to load balancer (if supported). |
| service.portName | string | `"http"` | Name for service port. |
| service.servicePort | int | `8085` | Service port to expose. |
| service.type | string | `"ClusterIP"` | Type of service to create. |
| serviceMonitor.annotations | object | `{}` | Annotations to add to service monitor |
| serviceMonitor.enabled | bool | `false` | If true, creates a Prometheus Operator ServiceMonitor. |
| serviceMonitor.interval | string | `"10s"` | Interval that Prometheus scrapes Cluster Autoscaler metrics. |
| serviceMonitor.metricRelabelings | object | `{}` | MetricRelabelConfigs to apply to samples before ingestion. |
| serviceMonitor.namespace | string | `"monitoring"` | Namespace which Prometheus is running in. |
| serviceMonitor.path | string | `"/metrics"` | The path to scrape for metrics; autoscaler exposes `/metrics` (this is standard) |
| serviceMonitor.relabelings | object | `{}` | RelabelConfigs to apply to metrics before scraping. |
| serviceMonitor.selector | object | `{"release":"prometheus-operator"}` | Default to kube-prometheus install (CoreOS recommended), but should be set according to Prometheus install. |
| tolerations | list | `[]` | List of node taints to tolerate (requires Kubernetes >= 1.6). |
| topologySpreadConstraints | list | `[]` | You can use topology spread constraints to control how Pods are spread across your cluster among failure-domains such as regions, zones, nodes, and other user-defined topology domains. (requires Kubernetes >= 1.19). |
| updateStrategy | object | `{}` | [Deployment update strategy](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#strategy) |
| vpa | object | `{"containerPolicy":{},"enabled":false,"recommender":"default","updateMode":"Auto"}` | Configure a VerticalPodAutoscaler for the cluster-autoscaler Deployment. |
| vpa.containerPolicy | object | `{}` | [ContainerResourcePolicy](https://github.com/kubernetes/autoscaler/blob/vertical-pod-autoscaler/v0.13.0/vertical-pod-autoscaler/pkg/apis/autoscaling.k8s.io/v1/types.go#L159). The containerName is always et to the deployment's container name. This value is required if VPA is enabled. |
| vpa.enabled | bool | `false` | If true, creates a VerticalPodAutoscaler. |
| vpa.recommender | string | `"default"` | Name of the VPA recommender that will provide recommendations for vertical scaling. |
| vpa.updateMode | string | `"Auto"` | [UpdateMode](https://github.com/kubernetes/autoscaler/blob/vertical-pod-autoscaler/v0.13.0/vertical-pod-autoscaler/pkg/apis/autoscaling.k8s.io/v1/types.go#L124) |
