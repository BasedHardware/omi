// Cortex model/provider selection + BYOK credentials + cloud-sync stub.
// Persisted via SharedPreferencesUtil. Flutter port of modelConfig.ts / cloudSync.ts.
import 'dart:convert';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/cortex/license.dart';
import 'package:omi/services/cortex/providers.dart';

enum CortexEngineMode { backend, provider }

class ResolvedTarget {
  final ProviderInfo provider;
  final ModelInfo? model;
  final String baseUrl;
  final String apiKey;
  const ResolvedTarget(this.provider, this.model, this.baseUrl, this.apiKey);
}

class CortexModelConfig {
  CortexModelConfig._();
  static final CortexModelConfig instance = CortexModelConfig._();

  final _prefs = SharedPreferencesUtil();

  CortexEngineMode get mode => _prefs.getString('cortexEngineMode', defaultValue: 'backend') == 'provider'
      ? CortexEngineMode.provider
      : CortexEngineMode.backend;
  set mode(CortexEngineMode v) => _prefs.saveString('cortexEngineMode', v == CortexEngineMode.provider ? 'provider' : 'backend');

  String? get providerId {
    final v = _prefs.getString('cortexProviderId');
    return v.isEmpty ? null : v;
  }

  set providerId(String? v) => _prefs.saveString('cortexProviderId', v ?? '');

  String? get modelId {
    final v = _prefs.getString('cortexModelId');
    return v.isEmpty ? null : v;
  }

  set modelId(String? v) => _prefs.saveString('cortexModelId', v ?? '');

  String? get customBaseUrl {
    final v = _prefs.getString('cortexCustomBaseUrl');
    return v.isEmpty ? null : v;
  }

  set customBaseUrl(String? v) => _prefs.saveString('cortexCustomBaseUrl', v ?? '');

  Map<String, String> get _apiKeys {
    try {
      final raw = _prefs.getString('cortexApiKeys');
      if (raw.isEmpty) return {};
      return Map<String, String>.from(jsonDecode(raw) as Map);
    } catch (_) {
      return {};
    }
  }

  String apiKey(String providerId) => _apiKeys[providerId] ?? '';

  void setApiKey(String providerId, String key) {
    final keys = _apiKeys;
    keys[providerId] = key;
    _prefs.saveString('cortexApiKeys', jsonEncode(keys));
  }

  /// Resolve the active provider target, or null when Cortex should use the
  /// default backend (mode backend, nothing configured, or missing required key).
  ResolvedTarget? resolveTarget() {
    if (mode != CortexEngineMode.provider || providerId == null) return null;
    final provider = cortexProviderById(providerId);
    if (provider == null) return null;
    final base = (provider.id == 'custom' ? (customBaseUrl ?? '') : provider.baseUrl).trim();
    if (base.isEmpty) return null;
    final key = apiKey(provider.id);
    if (provider.requiresApiKey && key.isEmpty) return null;
    return ResolvedTarget(provider, cortexModel(provider.id, modelId), base, key);
  }
}

/// Cloud sync — Pro feature, stub. Records intent + a local marker; the real
/// implementation will push an encrypted snapshot to cortex.apym.io.
class CortexCloudSync {
  CortexCloudSync._();
  static final CortexCloudSync instance = CortexCloudSync._();

  final _prefs = SharedPreferencesUtil();
  static const String endpoint = 'https://cortex.apym.io/api/sync';

  bool get enabled => _prefs.getString('cortexCloudSyncEnabled') == '1';
  set enabled(bool v) => _prefs.saveString('cortexCloudSyncEnabled', v ? '1' : '0');

  DateTime? get lastSyncedAt {
    final v = int.tryParse(_prefs.getString('cortexCloudSyncAt'));
    return v == null ? null : DateTime.fromMillisecondsSinceEpoch(v);
  }

  Future<({bool ok, String reason})> run() async {
    if (!CortexLicense.instance.hasFeature('cloud-sync')) {
      return (ok: false, reason: 'Cloud sync is a Cortex Pro feature.');
    }
    if (!enabled) return (ok: false, reason: 'Cloud sync is turned off.');
    // TODO: encrypt + POST snapshot to `endpoint`. Stubbed for now.
    _prefs.saveString('cortexCloudSyncAt', DateTime.now().millisecondsSinceEpoch.toString());
    return (ok: true, reason: 'Sync stub: snapshot recorded locally (upload not yet implemented).');
  }
}
