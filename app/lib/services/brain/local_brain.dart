import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// The local brain's routing layer, exposed from Kotlin over a MethodChannel.
///
/// Maps a free-text request to a phone action, or declines. This is deliberately
/// NOT a language model: on a Samsung SM-A145F a 270M function-calling LiteRT-LM
/// bundle routed at 22% with 72% refusals, 3120 ms and 983 MB peak RSS per prompt,
/// because it was failing at routing rather than generation. MiniLM-L6-v2 over the
/// same prompts routes at 67% held-out for ~600 ms and 285 MB.
///
/// Measured on a 3.5 GB device, so [route] is not a fast call. It is also not
/// safe to call concurrently with itself: the native side serialises onto one
/// thread because the CompiledModel's tensor buffers are reused in place.
class LocalBrain {
  LocalBrain._();

  static final LocalBrain instance = LocalBrain._();

  static const MethodChannel _channel = MethodChannel('com.friend.ios/local_brain');

  /// Action emitted when the router declines, or when a request is negated.
  static const String noAction = 'no_action';

  /// Action emitted when the request is to launch another app.
  static const String openApp = 'open_app';

  final ValueNotifier<bool> _ready = ValueNotifier<bool>(false);

  /// Whether the native model has been loaded. False until the first route.
  ValueListenable<bool> get ready => _ready;

  bool _loadInFlight = false;

  /// Loads the model up front. Optional: the first [route] loads it anyway.
  /// Takes a few seconds on a budget phone.
  Future<bool> warmUp() async {
    if (_ready.value || _loadInFlight) return _ready.value;
    _loadInFlight = true;
    try {
      final result = await _channel.invokeMapMethod<String, dynamic>('load');
      final ok = result?['ok'] == true;
      _ready.value = ok;
      if (!ok) {
        debugPrint('LocalBrain.load failed: ${result?['error']}');
      } else {
        debugPrint('LocalBrain loaded in ${result?['loadMs']}ms');
      }
      return ok;
    } on PlatformException catch (e) {
      debugPrint('LocalBrain.load threw: ${e.message}');
      return false;
    } finally {
      _loadInFlight = false;
    }
  }

  /// Routes [text] to an action.
  ///
  /// Returns `null` if the native side errored. Check [BrainDecision.declined]
  /// before acting: a decline is the router saying it does not know, and acting
  /// anyway is how an agent ends up doing the opposite of what was asked.
  Future<BrainDecision?> route(String text) async {
    try {
      final result = await _channel.invokeMapMethod<String, dynamic>('route', {'text': text});
      if (result == null || result['ok'] != true) {
        debugPrint('LocalBrain.route failed: ${result?['error']}');
        return null;
      }
      _ready.value = true;
      return BrainDecision(
        action: result['action'] as String? ?? noAction,
        margin: (result['margin'] as num?)?.toDouble() ?? 0.0,
        declined: result['declined'] == true,
        negated: result['negated'] == true,
        runnerUp: result['runnerUp'] as String? ?? '',
        latencyMs: (result['latencyMs'] as num?)?.toInt() ?? 0,
        reason: result['reason'] as String? ?? '',
      );
    } on PlatformException catch (e) {
      debugPrint('LocalBrain.route threw: ${e.message}');
      return null;
    }
  }

  /// Convenience: the action to execute, or null when the router declined.
  Future<String?> actionFor(String text) async {
    final decision = await route(text);
    if (decision == null || decision.declined) return null;
    return decision.action;
  }
}

class BrainDecision {
  const BrainDecision({
    required this.action,
    required this.margin,
    required this.declined,
    required this.negated,
    required this.runnerUp,
    required this.latencyMs,
    required this.reason,
  });

  /// The chosen action, even when [declined] is true — useful for diagnostics.
  final String action;

  /// Gap between the winner and the best alternative. This is the number to
  /// threshold on for an act-or-ask decision; accuracy is not.
  final double margin;

  /// True when the router would not commit: out of domain, ambiguous, or negated.
  final bool declined;

  /// True when a prohibition was detected and the request was refused outright.
  final bool negated;

  /// The action that came second, for the ambiguous-decline case.
  final String runnerUp;

  final int latencyMs;

  /// Why it declined, when it did.
  final String reason;

  @override
  String toString() => declined
      ? 'declined($action, margin=${margin.toStringAsFixed(3)}, $reason)'
      : '$action (margin=${margin.toStringAsFixed(3)}, ${latencyMs}ms)';
}
