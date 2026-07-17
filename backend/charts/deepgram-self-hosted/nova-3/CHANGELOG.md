# Changelog

All notable changes to this Helm chart will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## [0.24.0] - 2025-11-18

### Added

- Added `use_v2_language_detection` feature flag to support 36-language detection (disabled by default).

### Changed

- Updated default container tags to November 2025 release (`release-251118`). Refer to the [main Deepgram changelog](https://developers.deepgram.com/changelog/self-hosted-changelog#deepgram-self-hosted-november-2025-release-251118) for additional details.
- Updated `/v1/status` endpoint to raise four statuses: Initializing, Ready, Healthy, and Critical. See [status endpoint documentation](https://developers.deepgram.com/docs/self-hosted-status-endpoint) for details.

## [0.23.1] - 2025-11-04

### Fixed

- Quoted Voice Agent LLM model names to fix periods breaking the TOML parser

## [0.23.0] - 2025-10-29

### Changed

- Updated default container tags to October 2025 release (`release-251029`). Refer to the [main Deepgram changelog](https://developers.deepgram.com/changelog/self-hosted-changelog#deepgram-self-hosted-october-2025-release-251029) for additional details.
- Updated sample cluster configuration files to use Kubernetes 1.33 (previously 1.30)
- Updated Helm chart dependencies: cluster-autoscaler 9.52.1 (previously 9.46.3), prometheus-adapter 4.14.2 (previously 4.13.0)

### Fixed

- Fixed API templates to use correct `additionalLabels` reference

## [0.22.0] - 2025-10-15

### Added

- Added Google as a 3rd party provider for Voice Agent helm chart
- Added `topologySpreadConstraints`, which allows even distribution of pods from the same deployment across availability zones, among other criteria
- Added `redactUsage` under api features which enables redaction of usage metadata

### Changed

- Updated default container tags to October 2025 release (`release-251015`). Refer to the [main Deepgram changelog](https://developers.deepgram.com/changelog/self-hosted-changelog#deepgram-self-hosted-october-2025-release-251015) for additional details.
- Set `entity_redaction` to `true` by default, so redaction is automatically enabled if a valid NER model is available

## [0.21.0] - 2025-09-29

### Changed

- Updated default container tags to September 2025 release (`release-250929`). Refer to the [main Deepgram changelog](https://developers.deepgram.com/changelog/self-hosted-changelog#deepgram-self-hosted-september-2025-release-250929) for additional details.

## [0.20.0] - 2025-09-17

### Added

- Exposed the ability to add custom TOML sections in api.toml and engine.toml via `customToml`
- Added `nodeSelector` support for all components (API, Engine, License Proxy) to allow scheduling pods on specific nodes.
- Added configurable service types for API, Engine, and License Proxy services with ClusterIP as the default
- Added support for service annotations when using LoadBalancer service type
- Added `loadBalancerSourceRanges` configuration for LoadBalancer services to restrict access to specific IP CIDR ranges
- Added `externalTrafficPolicy` configuration for LoadBalancer services to control traffic routing behavior
- Updated sample configurations to demonstrate service configuration options including LoadBalancer security settings
- Container-level security context support to Helm templates
- Supported removing resource limits on Engine pods

### Changed

- Changed default service type from NodePort to ClusterIP for all services (API external, Engine metrics, License Proxy status)
- Updated service templates to support configurable service types and annotations

## [0.19.0] - 2025-09-12

### Added

- Changes the defaults of `.Values.api.features.formatEntityTags` and `.Values.engine.features.streamingNer` to `true`, so that NER formatting is enabled by default. This formatting is required with Nova-3 models. See our [self-hosted NER guide](https://deepgram.gitbook.io/help-center/self-hosted/how-can-i-enable-ner-formatting-in-my-self-hosted-deployment) for further details.
- Updated default container tags to September 2025 release (`release-250912`). Refer to the [main Deepgram changelog](https://developers.deepgram.com/changelog/self-hosted-changelog#deepgram-self-hosted-september-2025-release-250912) for additional details.

## [0.18.1] - 2025-09-03

### Added

- Defined `allowNonpublicEndpoints` Voice Agent flag for use with custom LLM endpoints

### Fixed

- Fixed HPA replica conflicts in API and Engine deployments by conditionally removing hardcoded replicas when autoscaling is enabled

## [0.18.0] - 2025-08-28

### Added

- Added built-in support for Voice Agent.
- Updated default container tags to August 2025 release (`release-250828`). Refer to the [main Deepgram changelog](https://developers.deepgram.com/changelog/self-hosted-changelog#deepgram-self-hosted-august-2025-release-250828) for additional details.

### Fixed

- Fixed securityContext template references for API and Engine deployments
- Fixed securityContext documentation comments

## [0.17.0] - 2025-08-14

### Added

- Updated default container tags to August 2025 release (`release-250814`). Refer to the [main Deepgram changelog](https://developers.deepgram.com/changelog/self-hosted-changelog#deepgram-self-hosted-august-2025-release-250814) for additional details.

## [0.16.0] - 2025-07-31

### Added

- Updated default container tags to July 2025 release (`release-250731`). Refer to the [main Deepgram changelog](https://developers.deepgram.com/changelog#deepgram-self-hosted-july-2025-release-250731) for additional details.

## [0.15.0] - 2025-07-10

### Added

- Apply additional annotations to the template section of Deployment resources.
- Updated default container tags to July 2025 release (`release-250710`). Refer to the [main Deepgram changelog](https://developers.deepgram.com/changelog#deepgram-self-hosted-july-2025-release-250710) for additional details.

## [0.14.0] - 2025-06-26

### Added

- Updated default container tags to June 2025 release (`release-250626`). Refer to the [main Deepgram changelog](https://deepgram.com/changelog/deepgram-self-hosted-june-2025-release-250626) for additional details.

## [0.13.0] - 2025-06-10

### Added

- Updated default container tags to June 2025 release. Refer to the [main Deepgram changelog](https://deepgram.com/changelog/deepgram-self-hosted-june-2025-release-250610) for additional details.

## [0.12.0] - 2025-03-31

### Added

- Updated default container tags to March 2025 release. Refer to the [main Deepgram changelog](https://deepgram.com/changelog/deepgram-self-hosted-march-2025-release-250331) for additional details.

## [0.11.1] - 2025-03-28

### Added

- Exposed configuration values to enable named-entity recognition models. See the [March 2025 Deepgram Self-Hosted Changelog](https://deepgram.com/changelog/deepgram-self-hosted-march-2025-release-250307) for more details on features powered by these models.

## [0.11.0] - 2025-03-07

### Added

- Updated default container tags to March 2025 release. Refer to the [main Deepgram changelog](https://deepgram.com/changelog/deepgram-self-hosted-march-2025-release-250307) for additional details.

## [0.10.0] - 2025-01-30

### Added

- Updated default container tags to January 2025 release. Refer to the [main Deepgram changelog](https://deepgram.com/changelog/deepgram-self-hosted-january-2025-release-250130) for additional details.

## [0.9.0] - 2024-12-26

### Added

- Updated default container tags to December 2024 release. Refer to the [main Deepgram changelog](https://deepgram.com/changelog/deepgram-self-hosted-december-2024-release-241226) for additional details.

## [0.8.1] - 2024-12-17

### Changed

- Fixed default ratio metrics in Prometheus Adapter chart values to use 0.0 to 1.0 scale to match autoscaling documentation

## [0.8.0] - 2024-11-21

### Added

- Updated default container tags to November 2024 release. Refer to the [main Deepgram changelog](https://deepgram.com/changelog/deepgram-self-hosted-november-2024-release-241121) for additional details.

### Fixed

- Add the Engine Deployment tolerations to the Engine's model download Job.

## [0.7.0] - 2024-10-24

### Added

- Updated default container tags to October 2024 release. Refer to the [main Deepgram changelog](https://deepgram.com/changelog/deepgram-self-hosted-october-2024-release-241024) for additional details. Highlights include:
  - Adds new [streaming websocket TTS](https://deepgram.com/changelog/websocket-text-to-speech-api)! This is a software feature, so no new TTS models are required.

### Changed

- AWS samples updated to take advantage of new [EKS accelerated AMIs](https://aws.amazon.com/about-aws/whats-new/2024/10/amazon-eks-nvidia-aws-neuron-instance-types-al2023/), which bundle the required NVIDIA driver and toolkit instead of being installed by the NVIDIA GPU operator 

## [0.6.0] - 2024-09-27

### Added

- Updated default container tags to September 2024 release. Refer to the [main Deepgram changelog](https://deepgram.com/changelog/deepgram-self-hosted-september-2024-release-240927) for additional details. Highlights include:
  - Adds broader support in Engine container for model auto-loading during runtime.
    - Filesystems that don't support `inotify`, such as `nfs`/`csi` PersistentVolumes in Kubernetes, can now load and unload models during runtime without requiring a Pod restart.
- Automatic model management on AWS now supports model removal. See the `engine.modelManager.models.remove` section in the `values.yaml` file for details.
- Container orchestrator environment variable added to improve support.

### Changed

- Automatic model downloads on AWS are moved from `engine.modelManager.models.links` to `engine.modelManager.models.add`. The old `links` field is still supported, but migration is recommended.

### Fixed

- Update sample files to fix an issue with sample command for Kubernetes Secret creation storing Quay credential
  - Previous command used `--from-file` with the user's Docker configuration file. Some local secret managers, like
    Apple Keychain, scrub this file for sensitive information, which would result in an empty secret being created.

## [0.5.0] - 2024-08-27

### Added

- Updated default container tags to August 2024 release. Refer to the [main Deepgram changelog](https://deepgram.com/changelog/deepgram-self-hosted-august-2024-release-240827) for additional details. Highlights include:
  - GA support for entity detection for pre-recorded English audio
  - GA support for improved redaction for pre-recorded English audio

### Fixed

- Fixed a misleading comment in the `03-basic-setup-onprem.yaml` sample file that wrongly suggested `engine.modelManager.volumes.customVolumeClaim.name` should be a `PersistentVolume` instead of a `PersistentVolumeClaim`

### Changed

- Deepgram's core products are available to host both on-premises and in the cloud. Official resources have been updated to refer to a ["self-hosted" product offering](https://deepgram.com/self-hosted), instead of an "onprem" product offering, to align the product name with industry naming standards. The Deepgram Quay image repository names have been updated to reflect this.

## [0.4.0] - 2024-07-25

### Added

- Introduced entity detection feature flag for API containers (`false` by default).
- Updated default container tags to July 2024 release. Refer to the [main Deepgram changelog](https://deepgram.com/changelog/deepgram-self-hosted-july-2024-release-240725) for additional details. Highlights include:
  - Support for Deepgram's new English/Spanish multilingual code-switching model
  - Beta support for entity detection for pre-recorded English audio
  - Beta support for improved redaction for pre-recorded English audio
  - Beta support for improved entity formatting for streaming English audio

### Removed

- Removed some items nested under `api.features` and `engine.features` sections in favor of opinionated defaults.

## [0.3.0] - 2024-07-18

### Added

- Allow specifying custom annotations for deployments.

## [0.2.3] - 2024-07-15

### Added

- Sample `values.yaml` file for on-premises/self-managed Kubernetes clusters.

### Fixed

- Resolves a mismatch between PVC and SC prefix naming convention.
- Resolves error when specifying custom service account names.

### Changed

- Make `imagePullSecrets` optional.

## [0.2.2-beta] - 2024-06-27

### Added

- Adds more verbose logging for audio content length.
- Keeps our software up-to-date.
- See the [changelog](https://deepgram.com/changelog/deepgram-on-premises-june-2024-release-240627) associated with this routine monthly release.

## [0.2.1-beta] - 2024-06-24

### Added

- Restart Deepgram containers automatically when underlying ConfigMaps have been modified.

## [0.2.0-beta] - 2024-06-20

### Added
- Support for managing node autoscaling with [cluster-autoscaler](https://github.com/kubernetes/autoscaler).
- Support for pod autoscaling of Deepgram components.
- Support for keeping the upstream Deepgram License server as a backup even when the License Proxy is deployed. See `licenseProxy.keepUpstreamServerAsBackup` for details.

### Changed

- Initial installation replica count values moved from `scaling.static.{api,engine}.replicas` to `scaling.replicas.{api,engine}`.
- License Proxy is no longer manually scaled. Instead, scaling can be indirectly controlled via `licenseProxy.{enabled,deploySecondReplica}`.
- Labels for Deepgram dedicated nodes in the sample `cluster-config.yaml` for AWS, and the `nodeAffinity` sections of the sample `values.yaml` files. The key has been renamed from `deepgram/nodeType` to `k8s.deepgram.com/node-type`, and the values are no longer prepended with `deepgram`.
- AWS EFS model download job hook delete policy changed to `before-hook-creation`.
- Concurrency limit moved from API (`api.concurrencyLimit.activeRequests`) to Engine level (`engine.concurrencyLimit.activeRequests`).

## [0.1.1-alpha] - 2024-06-03

### Added

- Various documentation improvements

## [0.1.0-alpha] - 2024-05-31

### Added

- Initial implementation of the Helm chart.


[unreleased]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.23.0...HEAD
[0.23.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.22.0...deepgram-self-hosted-0.23.0
[0.22.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.21.0...deepgram-self-hosted-0.22.0
[0.21.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.20.0...deepgram-self-hosted-0.21.0
[0.20.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.19.0...deepgram-self-hosted-0.20.0
[0.19.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.18.1...deepgram-self-hosted-0.19.0
[0.18.1]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.18.0...deepgram-self-hosted-0.18.1
[0.18.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.17.0...deepgram-self-hosted-0.18.0
[0.17.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.16.0...deepgram-self-hosted-0.17.0
[0.16.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.15.0...deepgram-self-hosted-0.16.0
[0.15.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.14.0...deepgram-self-hosted-0.15.0
[0.14.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.13.0...deepgram-self-hosted-0.14.0
[0.13.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.12.0...deepgram-self-hosted-0.13.0
[0.12.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.11.1...deepgram-self-hosted-0.12.0
[0.11.1]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.11.0...deepgram-self-hosted-0.11.1
[0.11.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.10.0...deepgram-self-hosted-0.11.0
[0.10.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.9.0...deepgram-self-hosted-0.10.0
[0.9.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.8.1...deepgram-self-hosted-0.9.0
[0.8.1]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.8.0...deepgram-self-hosted-0.8.1
[0.8.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.7.0...deepgram-self-hosted-0.8.0
[0.7.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.6.0...deepgram-self-hosted-0.7.0
[0.6.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.5.0...deepgram-self-hosted-0.6.0
[0.5.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.4.0...deepgram-self-hosted-0.5.0
[0.4.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.3.0...deepgram-self-hosted-0.4.0
[0.3.0]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.2.3...deepgram-self-hosted-0.3.0
[0.2.3]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.2.2-beta...deepgram-self-hosted-0.2.3
[0.2.2-beta]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.2.1-beta...deepgram-self-hosted-0.2.2-beta
[0.2.1-beta]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.2.0-beta...deepgram-self-hosted-0.2.1-beta
[0.2.0-beta]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.1.1-alpha...deepgram-self-hosted-0.2.0-beta
[0.1.1-alpha]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.1.0-alpha...deepgram-self-hosted-0.1.1-alpha
[0.1.0-alpha]: https://github.com/deepgram/self-hosted-resources/releases/tag/deepgram-self-hosted-0.1.0-alpha


