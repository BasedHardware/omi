// Cortex open-core licensing (Flutter port of shared/license.ts).
//
// Cortex is open source and free. A Pro tier (with a one-time 14-day trial)
// unlocks cloud sync, higher automation limits and priority model routing.
// Persisted via SharedPreferencesUtil.
import 'package:omi/backend/preferences.dart';

enum CortexTier { free, trial, pro }

const Duration kTrialDuration = Duration(days: 14);

class ProFeature {
  final String id;
  final String label;
  final String description;
  const ProFeature(this.id, this.label, this.description);
}

const List<ProFeature> kProFeatures = [
  ProFeature('cloud-sync', 'Cloud sync', 'Encrypted sync of your conversations, memories and settings across devices.'),
  ProFeature('priority-models', 'Priority models', 'Pin premium cloud models and get priority routing.'),
  ProFeature('team', 'Team workspaces', 'Shared memories and goals for your team (coming soon).'),
];

final RegExp _proKeyRe = RegExp(r'^CORTEX-PRO-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$');

bool isValidProKey(String? key) {
  if (key == null) return false;
  return _proKeyRe.hasMatch(key.trim().toUpperCase());
}

/// Cortex license state + tier math. Singleton over SharedPreferences.
class CortexLicense {
  CortexLicense._();
  static final CortexLicense instance = CortexLicense._();

  final _prefs = SharedPreferencesUtil();

  String get _proKey => _prefs.getString('cortexProKey');
  set _proKeyStore(String v) => _prefs.saveString('cortexProKey', v);

  int get _trialStartedAt => int.tryParse(_prefs.getString('cortexTrialStartedAt')) ?? 0;
  set _trialStartedAtStore(int v) => _prefs.saveString('cortexTrialStartedAt', v.toString());

  DateTime? get trialEndsAt =>
      _trialStartedAt == 0 ? null : DateTime.fromMillisecondsSinceEpoch(_trialStartedAt).add(kTrialDuration);

  bool isTrialActive([DateTime? now]) {
    final ends = trialEndsAt;
    if (ends == null) return false;
    return (now ?? DateTime.now()).isBefore(ends);
  }

  int trialDaysRemaining([DateTime? now]) {
    final ends = trialEndsAt;
    if (ends == null) return 0;
    final ms = ends.difference(now ?? DateTime.now()).inMilliseconds;
    if (ms <= 0) return 0;
    return (ms / Duration.millisecondsPerDay).ceil();
  }

  CortexTier get tier {
    if (isValidProKey(_proKey)) return CortexTier.pro;
    if (isTrialActive()) return CortexTier.trial;
    return CortexTier.free;
  }

  bool get isProActive => tier == CortexTier.pro || tier == CortexTier.trial;

  bool hasFeature(String _) => isProActive;

  bool get canStartTrial => _trialStartedAt == 0 && !isValidProKey(_proKey);

  bool startTrial() {
    if (!canStartTrial) return false;
    _trialStartedAtStore = DateTime.now().millisecondsSinceEpoch;
    return true;
  }

  bool redeemProKey(String key) {
    if (!isValidProKey(key)) return false;
    _proKeyStore = key.trim().toUpperCase();
    return true;
  }

  void clear() {
    _proKeyStore = '';
    _trialStartedAtStore = 0;
  }
}
