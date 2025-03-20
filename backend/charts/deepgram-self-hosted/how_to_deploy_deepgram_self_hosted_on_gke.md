# How to Deploy Deepgram Self-Hosted on GKE

## Hardware Specifications

### Engine
- A NVIDIA GPU
  - Minimum compute capability: 7.0+
  - 16 GB GPU RAM
  - Recommended on the Cloud: NVIDIA L4 GPUs (powerful balance between price and performance)
    - GCP - g2 series
    - Other commonly used cloud GPUs: NVIDIA T4, NVIDIA A10
- 4 CPU cores
- 32 GB system RAM
  - You may be able to run Deepgram services with only 16 GB of system RAM if you are only using a small number of models. Please contact Support to see if this is possible for your use case.
- 48 GB storage
  - We recommend more if you intend on deploying multiple models.

### API
- 2 CPU cores
- 4 GB system RAM

### License Proxy
- 1 vCPUs (Limit: 2 vCPUs)
- At least 5 GB RAM (Request: 1 GB RAM. Limit: 8 GB RAM)

## Operating System
Deepgram's self-hosted products run on the Linux operating system. The following distributions are officially supported:

- Ubuntu Server 22.04/24.04
- Red Hat Enterprise Linux (RHEL) 8/9
- Oracle Linux 8/9

## Prerequisites

### Tools
- kubectl
- gcloud CLI
- helm

## Deployment Steps

### I. Create License for running Self-Hosted Deepgram in Deepgram console
- **Self-Hosted API Key**
- **Distribution Credentials**: Distribution credentials are used to authenticate with a container image repository when pulling Deepgram container images into your deployment environment.

### II. Create Private Container Registry for self-hosted Deepgram container

#### 1. Pulling Images from Quay
- Generate credentials to authenticate with Quay
- Login to Quay:
  ```bash
  docker login quay.io <USERNAME>
  ```
- Identify the latest self-hosted release in the Deepgram Changelog. Filter by "Self-Hosted", and select the latest release.
  https://deepgram.com/changelog/
- Pull the relevant container images:
  ```bash
  export RELEASE_TAG=<LATEST_RELEASE_TAG>

  docker pull quay.io/deepgram/self-hosted-api:$RELEASE_TAG
  docker pull quay.io/deepgram/self-hosted-engine:$RELEASE_TAG
  docker pull quay.io/deepgram/self-hosted-license-proxy:$RELEASE_TAG
  ```

> Note: Replace `<LATEST_RELEASE_TAG>` with the tag of the latest release from the Changelog.

#### 2. Create a container image repository
```bash
export GCP_REGION="<GCP_REGION>"
export GCP_PROJECT="<GCP_PROJECT>"

gcloud artifacts repositories create deepgram \
    --repository-format=docker \
    --location="$GCP_REGION" \
    --description="Private repository for storing Deepgram container images" \
    --project="$GCP_PROJECT"
```

#### 3. Authenticate your local Docker agent with your new GCP container registry
```bash
gcloud auth configure-docker "$GCP_REGION-docker.pkg.dev"
# If you use `root` to access docker, i.e. `sudo docker...`, make sure
# to run this command with `sudo` as well
# sudo gcloud auth configure-docker "$GCP_REGION-docker.pkg.dev"
```

```bash
API_REPO_URI="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT/deepgram/self-hosted-api"
ENGINE_REPO_URI="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT/deepgram/self-hosted-engine"
LICENSE_PROXY_REPO_URI="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT/deepgram/self-hosted-license-proxy"
```

#### 4. Pushing Images to Private Registry
Push your local copy of the Deepgram container, previously pulled from Quay, to your private registry.
```bash
docker tag "quay.io/deepgram/self-hosted-api:$RELEASE_TAG" "$API_REPO_URI:$RELEASE_TAG"
docker tag "quay.io/deepgram/self-hosted-engine:$RELEASE_TAG" "$ENGINE_REPO_URI:$RELEASE_TAG"
docker tag "quay.io/deepgram/self-hosted-license-proxy:$RELEASE_TAG" "$LICENSE_PROXY_REPO_URI:$RELEASE_TAG"

docker push "$API_REPO_URI:$RELEASE_TAG"
docker push "$ENGINE_REPO_URI:$RELEASE_TAG"
docker push "$LICENSE_PROXY_REPO_URI:$RELEASE_TAG"
```

#### 5. Configuring Deployment to Use Private Registry
Modify your `values.yaml` file for the deepgram-self-hosted Helm chart to use the new image path:
```yaml
api:
  image:
    path: IMAGE_PATH
    tag: IMAGE_TAG
```

> Note: Replace `IMAGE_PATH` and `IMAGE_TAG` with the output of: 
```bash
echo "$API_REPO_URI"
echo "$RELEASE_TAG"
```

### III. Prepare network environment for creating API ingress

#### 1. Create a proxy-only subnet
```bash
CLUSTER_LOCATION="<CLUSTER_LOCATION>"
CLUSTER_NETWORK="<CLUSTER_NETWORK>"
CLUSTER_SUBNETWORK="<CLUSTER_SUBNETWORK>"
CONTAINER_PORT=8080
PROXY_ONLY_SUBNET="<PROXY_ONLY_SUBNET>"
PROXY_ONLY_SUBNET_NAME="PROXY_ONLY_SUBNET_NAME"
ALLOW_PROXY_CONN_FIREWALL="<FIREWALL_NAME>"
DG_INTERNAL_LB_IP_ADDR="<IP_ADDRESS>"


gcloud compute networks subnets create $PROXY_ONLY_SUBNET_NAME \
    --purpose=REGIONAL_MANAGED_PROXY \
    --role=ACTIVE \
    --region=$CLUSTER_LOCATION \
    --network=$CLUSTER_NETWORK \
    --range=$PROXY_ONLY_SUBNET
````
#### 2. Create a firewall rule
The Ingress controller does not create a firewall rule to allow connections from the load balancer proxies in the proxy-subnet.
Create a firewall rule to allow connections from the load balancer proxies in the proxy-only subnet to the pod listening port:
```bash
gcloud compute firewall-rules create $ALLOW_PROXY_CONN_FIREWALL \
    --allow=TCP:$CONTAINER_PORT \
    --source-ranges=$PROXY_ONLY_SUBNET \
    --network=$CLUSTER_NETWORK
```

#### 3. Create internal static IP address for ingress
```bash
gcloud compute addresses create prod-omi-deepgram-ilb-ip-address \
  --region=$CLUSTER_LOCATION \
  --subnet=$CLUSTER_SUBNETWORK \
  --addresses=$DG_INTERNAL_LB_IP_ADDR
```

### IV. Create self-managed certificate for internal Deepgram ALB

#### 1. Purchase a self-managed certificate from public CA for internal ALB

#### 2. Create the regional certificate
```bash
gcloud compute ssl-certificates create <CERT_NAME> \
    --certificate <CERT_BUNDLE_FILE_PATH> \
    --private-key <KEY_FILE_PATH> \
    --region <COMPUTE_REGION>
```

> **Notes:** Certificates bundle file must includes both SSL cert and CA certs

#### 3. Create new DNS record for Deepgram self-hosted internal ALB
`dg.omi.me` => Point to internal static IP address

### V. Create Google-managed certificate and external IP for Grafana

#### 1. Create external IP for Grafana
```bash
DG_GRAFANA_ALB_IP_ADDR="<DG_GRAFANA_ALB_IP_ADDR>"

gcloud compute addresses create $DG_GRAFANA_ALB_IP_ADDR --global
gcloud compute addresses describe $DG_GRAFANA_ALB_IP_ADDR --global
# Get the external IP address and save it for later use.
```

#### 2. Create Google-managed certificate for Grafana ALB
```bash
kubectl apply -f prod_omi_deepgram_grafana_alb_cert.yaml
```

#### 3. Create new DNS record for Grafana
`dg-monitor.omi.me` => Point to above external IP address

## Steps to deploy self-hosted Deepgram to Kubernetes (GKE)

### I. Creating a Cluster

#### 1. Create a new GKE cluster with gcloud, and get the zones where your cluster is created
```bash
CLUSTER_NAME="<CLUSTER_NAME>"
CLUSTER_LOCATION="<CLUSTER_LOCATION>"
CLUSTER_NETWORK="<CLUSTER_NETWORK>"
CLUSTER_SUBNETWORK="<CLUSTER_SUBNETWORK>"

gcloud container clusters create $CLUSTER_NAME \
    --location $CLUSTER_LOCATION \
    --network $CLUSTER_NETWORK \
    --subnetwork $CLUSTER_SUBNETWORK \
    --enable-ip-alias \
    --node-locations "${CLUSTER_LOCATION}-a" \
    --num-nodes 1 \
    --enable-autoscaling \
    --enable-image-streaming \
    --machine-type n2-standard-2 \
    --addons=GcePersistentDiskCsiDriver,HttpLoadBalancing

CLUSTER_ZONES=$(
     gcloud container clusters describe $CLUSTER_NAME \
         --location $CLUSTER_LOCATION \
         --format="value(locations.join(','))"
)
ENGINE_NP_ZONE=$(echo "$CLUSTER_ZONES" | cut -d',' -f1)
```

#### 2. Create separate node pools for each Deepgram component (API, Engine, License Proxy)
Adjust the machine types and node counts according to your needs. You may wish to consult your Deepgram Account Representative in planning your cluster's capacity.
```bash
gcloud container node-pools create api-pool \
    --cluster $CLUSTER_NAME \
    --location $CLUSTER_LOCATION \
    --num-nodes 1 \
    --enable-autoscaling \
    --max-nodes 8 \
    --machine-type n2-standard-4 \
    --node-labels k8s.deepgram.com/node-type=api
  
gcloud container node-pools create engine-pool \
    --cluster $CLUSTER_NAME \
    --region $CLUSTER_LOCATION \
    --node-locations $ENGINE_NP_ZONE \
    --num-nodes 1 \
    --enable-autoscaling \
    --max-nodes 8 \
    --machine-type g2-standard-12 \
    --accelerator=type=nvidia-l4,count=1,gpu-driver-version=latest \
    --node-labels k8s.deepgram.com/node-type=engine
  
gcloud container node-pools create license-proxy-pool \
    --cluster $CLUSTER_NAME \
    --location $CLUSTER_LOCATION \
    --num-nodes 1 \
    --enable-autoscaling \
    --max-nodes 2 \
    --machine-type n2-standard-2 \
    --node-labels k8s.deepgram.com/node-type=license-proxy
```

> **Notes:**
> - `num-nodes` configures the number of nodes in the node pool in each of the cluster's zones. If your cluster is configured in 3 zones, setting `num-nodes` to 1 will result in 1 node per zone, or 3 nodes across the entire cluster.
> - We restrict the engine-pool to one cluster zone because you can't use regional persistent disks on VMs that use G2 standard machine types. This guide uses a zonal persistent disk as a workaround, which means we must limit the nodes in engine-pool to a single zone in order to mount the disk.

#### 3. Create a dedicated namespace for Deepgram resources
```bash
DG_NAMESPACE="<DG_NAMESPACE>"

kubectl create namespace $DG_NAMESPACE
kubectl config set-context --current --namespace=$DG_NAMESPACE
```

### II. Configure Persistent Storage

#### 1. Create a Google Persistent Disk to store Deepgram model files and share them across multiple Deepgram Engine pods
```bash
DISK_NAME="<DISK_NAME>"
DISK_URI=$(
    gcloud compute disks create \
        $DISK_NAME \
        --size=200GB \
        --type=pd-ssd \
        --zone $ENGINE_NP_ZONE \
        --format="value(selfLink)" | \
    sed -e 's#.*/projects/#projects/#'
)
```

#### 2. Create a temporary VM instance in one of your cluster's zones and attach the persistent disk
```bash
gcloud compute instances create model-downloader \
    --machine-type=n1-standard-1 \
    --zone $ENGINE_NP_ZONE \
    --disk=name=$DISK_URI,scope=zonal,device-name=$DISK_NAME,mode=rw,boot=no
```

#### 3. SSH into the VM instance
```bash
gcloud compute ssh model-downloader \
    --zone $ENGINE_NP_ZONE
```

> **Note:** You can use SSH via gcloud console web

#### 4. In the VM, format and mount the disk, then download the model files provided by your Deepgram Account Representative onto the disk
```bash
DISK_NAME="<DISK_NAME>"
sudo mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard \
    /dev/disk/by-id/google-$DISK_NAME

MOUNT_PATH=/mnt/disks/models
sudo mkdir -p $MOUNT_PATH
sudo mount -o discard,defaults /dev/disk/by-id/google-$DISK_NAME $MOUNT_PATH
sudo chmod a+w $MOUNT_PATH
cd $MOUNT_PATH

# Download each model file
wget https://link-to-model-1.dg
wget https://link-to-model-2.dg
# ... continue for all model files
```

#### 5. Unmount the disk and delete the temporary VM instance
```bash
cd
sudo umount $MOUNT_PATH
exit

gcloud compute instances delete model-downloader \
    --zone $ENGINE_NP_ZONE
```

### III. Configure Kubernetes Secrets
The deepgram-self-hosted Helm chart takes two Secret references:
- One is a set of distribution credentials that allow the cluster to pull images from Deepgram's container image repository.
- The other is your self-hosted API key that licenses each Deepgram container that is created.

#### 1. If not using an external Secret store provider, create the Secrets manually in your cluster
- Using the distribution credentials username and password generated in the Deepgram Console, create a Kubernetes Secret named `dg-regcred`
  ```bash
  kubectl create secret docker-registry dg-regcred \
      --docker-server=quay.io \
      --docker-username='QUAY_DG_USER' \
      --docker-password='QUAY_DG_PASSWORD'
  ```

> Replace the placeholders `QUAY_DG_USER` and `QUAY_DG_PASSWORD` with the distribution credentials you generated in the Deepgram console.

- Create a Kubernetes Secret named `dg-self-hosted-api-key` to store your self-hosted API key
  ```bash
  kubectl create secret generic dg-self-hosted-api-key \
      --from-literal=DEEPGRAM_API_KEY='<YOUR_API_KEY_HERE>'
  ```

### IV. Deploy Deepgram

#### 1. Install the Helm Chart with your `values.yaml` file
```bash
helm upgrade --install <HELM_RELEASE_NAME> ./deepgram-self-hosted \
    -f ./deepgram-self-hosted/prod_omi_values.yaml \
    --namespace <DG_NAMESPACE> \
    --atomic \
    --timeout 1h

# Monitor the installation in a separate shell
watch kubectl get all
```

### V. Test Your Deepgram Setup with a Sample Request

#### 1. Get the name of one of the Deepgram API Pods
```bash
API_POD_NAME=$(
    kubectl get pods \
        --selector app=deepgram-api \
        --output jsonpath='{.items[0].metadata.name}' \
        --no-headers
)
```

#### 2. Launch an ephemeral container to send your test request from
```bash
kubectl debug $API_POD_NAME \
    -it \
    --image=curlimages/curl \
    -- /bin/sh
```

#### 3. Inside the ephemeral container, download a sample file from Deepgram (or supply your own file)
```bash
wget https://dpgr.am/bueller.wav
```

#### 4. Send your audio file to your local Deepgram setup for transcription
```bash
curl \
    -X POST \
    --data-binary @bueller.wav \
    "http://localhost:8080/v1/listen?model=nova-2&smart_format=true"
```

### VI. Auto scaling

#### Scaling components
- Engine containers, which handle inference tasks
- API containers, which handle request brokering to the Engine containers, as well as some post-processing coordination.
  - Each API container can generally support up to 16 Engine containers, with a more typical ratio of 1:4. However, some customers choose to deploy API instances 1:1 with Engine, as the API container is comparatively lightweight.

#### Container Image Cache
It is important to consider where the container images are pulled from when scaling out your deployment to new nodes, as this will impact the time required to scale

#### For streaming speech-to-text, monitor
- `engine_active_requests{kind="stream"}`
- `engine_estimated_stream_capacity` (optional)

#### Enforcing Limits
Limit requests to Engine

This can be accomplished by setting a maximum request limit in your Engine configurations (`engine.toml`) with the `max_active_requests` value. In the deepgram-self-hosted Helm chart, this value is controlled by the `engine.concurrencyLimit.activeRequests` configuration value. Incoming requests to an Engine instance beyond this limit will return an error instead of slowing down other requests.

When an API instance receives a request and assigns inference work to a downstream Engine instance, that Engine instance may return an error if it is over capacity. The API instance will then attempt to retry the request with other Engine instances, if available. If no Engine instance is available to meet the request, after exhausting all retry attempts, the API instance will ultimately return a 503 HTTP response back to the calling application giving confirmation of the failure.

#### Auto scaling in Deepgram Helm chart
https://github.com/deepgram/self-hosted-resources/tree/main/charts/deepgram-self-hosted#autoscaling

### VII. System Maintenance
- Renewing self-managed certificate before it expires
- Updating Models
- Installing Product Updates (Deepgram container via Helm chart)
- Updating Configuration Files
- Managing Deepgram Licenses
- Backing up Deepgram Products: Using Velero (https://velero.io/)
- Optimizing auto-scaling settings for performance and cost efficiency