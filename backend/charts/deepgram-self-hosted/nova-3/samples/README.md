# Samples

This directory contains examples of how to use the Deepgram Helm chart in various configurations and with various cloud providers. The samples are not meant to be an exhaustive demonstration of all available options; please see the chart [README](../README.md) and [values.yaml](../values.yaml) for more information.

## Available Samples

- **01-basic-setup-aws.values.yaml** - Basic AWS EKS deployment configuration
- **02-basic-setup-gcp.yaml** - Basic GCP GKE deployment configuration  
- **03-basic-setup-onprem.yaml** - On-premises deployment configuration
- **04-aura-2-setup.yaml** - Aura-2 model deployment with English and Spanish language support
- **05-voice-agent-aws.values.yaml** - AWS EKS Voice Agent deployment configuration

## AWS EKS Samples
See the [Deepgram AWS EKS guide](https://developers.deepgram.com/docs/aws-k8s) for detailed instructions on how to deploy Deepgram services in a managed Kubernetes cluster in AWS.

## GCP GKE Samples
See the [Deepgram GCP GKE guide](https://developers.deepgram.com/docs/gcp-k8s) for detailed instructions on how to deploy Deepgram services in a managed Kubernetes cluster in GCP.

## Aura-2 Deployment
For deploying Aura-2 models, use the `04-aura-2-setup.yaml` sample configuration. This configuration includes:

- Aura-2 specific environment variables and UUIDs
- Multi-language support (English and Spanish)
- GPU resource allocation
- Model management configuration
- License proxy setup for production deployments

To deploy with Aura-2 support:
```bash
helm install deepgram ./charts/deepgram-self-hosted -f samples/04-aura-2-setup.yaml
```
