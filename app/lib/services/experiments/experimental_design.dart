import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

/// The experimental design: one switch for a set of look changes that ship dark.
///
/// What it changes today:
/// - the floating controls at the bottom of Home (Ask anything, record, the recording bar) and of
///   the conversation page (Ask Omi, the audio player, End Conversation) are frosted surfaces with
///   a soft shadow that show the content scrolling behind them, and the page-coloured block those
///   screens paint under the row is left out or softened;
/// - conversation rows have no card behind them, a larger icon tile and larger title and subtitle.
/// - a conversation in progress has one page, whether or not the server has made it yet: the live
///   page draws the conversation page's layout (Summary and Transcript) and becomes the
///   conversation's page in place once the server lists it (`LiveEpisodePage`).
///
/// On for a person who turns it on in Developer Settings, and for an account the Omi flag
/// [enabledFlag] admits. Lifecycle: rollout; default off; off while the flag is unknown.
abstract final class ExperimentalDesign {
  static const enabledFlag = 'mobile-experimental-design';
  static const prefKey = 'experimentalDesignEnabled';

  static final ValueNotifier<bool> _active = ValueNotifier(false);
  static bool _flag = false;
  static bool _started = false;

  /// Tests set this to exercise either look.
  @visibleForTesting
  static bool? debugOverride;

  /// The Developer Settings choice, kept on this phone.
  static bool get manual => SharedPreferencesUtil().getBool(prefKey);

  static set manual(bool value) {
    SharedPreferencesUtil().saveBool(prefKey, value);
    _sync();
  }

  /// Whether the account's flag turns the design on, whatever the Developer Settings choice.
  static bool get byFlag => _flag;

  /// The current answer without subscribing. A widget's build should use [of].
  static bool get enabled => debugOverride ?? _active.value;

  /// The current answer; under an [ExperimentalDesignScope] the widget rebuilds when it changes.
  static bool of(BuildContext context) {
    context.dependOnInheritedWidgetOfExactType<ExperimentalDesignScope>();
    return enabled;
  }

  /// Called once at startup, after preferences have loaded. Reads the saved choice and follows the
  /// account's flag from then on: read again whenever the analytics identity settles or changes.
  static void start() {
    _sync();
    if (_started) return;
    _started = true;
    AnalyticsManager.settledIdentity.addListener(_readFlag);
    _readFlag();
  }

  static int _read = 0;

  static Future<void> _readFlag() async {
    final read = ++_read;
    var flag = false;
    if (AnalyticsManager.settledIdentity.value != null) {
      try {
        flag = await AnalyticsManager().refreshBooleanFeatureFlag(enabledFlag);
      } catch (_) {
        flag = false;
      }
    }
    if (read != _read) return;
    _flag = flag;
    _sync();
  }

  /// Tests: what a flag read would have set.
  @visibleForTesting
  static void debugSetFlag(bool flag) {
    _flag = flag;
    _sync();
  }

  static void _sync() {
    var manual = false;
    try {
      manual = ExperimentalDesign.manual;
    } catch (_) {
      // Preferences not loaded (a test without them): the saved choice reads as off.
    }
    _active.value = manual || _flag;
  }
}

/// A conversation row's title: the theme's, or 17pt semibold in the experimental design.
TextStyle? experimentalRowTitleStyle(BuildContext context) {
  final style = Theme.of(context).textTheme.titleMedium;
  return ExperimentalDesign.of(context) ? style?.copyWith(fontSize: 17, fontWeight: FontWeight.w600) : style;
}

/// Rebuilds the widgets that read [ExperimentalDesign.of] when the answer changes. One at the root
/// of the app.
class ExperimentalDesignScope extends InheritedNotifier<ValueNotifier<bool>> {
  ExperimentalDesignScope({super.key, required super.child}) : super(notifier: ExperimentalDesign._active);
}
