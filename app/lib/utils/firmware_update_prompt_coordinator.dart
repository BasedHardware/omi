import 'package:flutter/foundation.dart';

@immutable
class FirmwareUpdatePrompt {
  const FirmwareUpdatePrompt._({required this.id, required this.version});

  final int id;
  final String version;
}

class FirmwareUpdatePromptCoordinator {
  int _nextPromptId = 0;
  String? _availableVersion;
  String? _deferredVersion;
  _ActiveFirmwareUpdatePrompt? _activePrompt;

  void setAvailableVersion(String? version) {
    final normalizedVersion = version?.trim();
    if (normalizedVersion == null || normalizedVersion.isEmpty) {
      _availableVersion = null;
      _deferredVersion = null;
      _requestActiveDismissal();
      return;
    }

    if (_availableVersion != null && _availableVersion != normalizedVersion) {
      _requestActiveDismissal();
    }
    _availableVersion = normalizedVersion;
  }

  FirmwareUpdatePrompt? beginPresentation() {
    final version = _availableVersion;
    if (version == null || version == _deferredVersion || _activePrompt != null) {
      return null;
    }

    final prompt = FirmwareUpdatePrompt._(id: _nextPromptId++, version: version);
    _activePrompt = _ActiveFirmwareUpdatePrompt(prompt);
    return prompt;
  }

  void attachDismissal(FirmwareUpdatePrompt prompt, VoidCallback dismiss) {
    final activePrompt = _activePrompt;
    if (activePrompt == null || activePrompt.prompt.id != prompt.id) {
      dismiss();
      return;
    }

    activePrompt.dismiss = dismiss;
    if (activePrompt.dismissalRequested) {
      dismiss();
    }
  }

  bool defer(FirmwareUpdatePrompt prompt) {
    final activePrompt = _activePrompt;
    if (activePrompt == null || activePrompt.prompt.id != prompt.id) {
      return false;
    }

    _deferredVersion = prompt.version;
    _requestActiveDismissal();
    return true;
  }

  bool accept(FirmwareUpdatePrompt prompt) {
    final activePrompt = _activePrompt;
    if (activePrompt == null || activePrompt.prompt.id != prompt.id) {
      return false;
    }

    _requestActiveDismissal();
    return true;
  }

  void invalidatePresentation() {
    _requestActiveDismissal();
  }

  void complete(FirmwareUpdatePrompt prompt) {
    if (_activePrompt?.prompt.id == prompt.id) {
      _activePrompt = null;
    }
  }

  void _requestActiveDismissal() {
    final activePrompt = _activePrompt;
    if (activePrompt == null || activePrompt.dismissalRequested) {
      return;
    }

    activePrompt.dismissalRequested = true;
    activePrompt.dismiss?.call();
  }
}

class _ActiveFirmwareUpdatePrompt {
  _ActiveFirmwareUpdatePrompt(this.prompt);

  final FirmwareUpdatePrompt prompt;
  VoidCallback? dismiss;
  bool dismissalRequested = false;
}
