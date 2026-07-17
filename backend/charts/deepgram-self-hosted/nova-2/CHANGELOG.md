# Changelog

All notable changes to this Helm chart will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

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


[unreleased]: https://github.com/deepgram/self-hosted-resources/compare/deepgram-self-hosted-0.10.0...HEAD
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


