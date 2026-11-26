// Reliability experiments: candidate behaviour changes that stay off unless switched on.
//
// The released app's behaviour is the baseline. A proposed change to it lives
// in the same function it changes, behind `ReliabilityExperiments.enabled`,
// and does nothing until it is switched on. Mirrors
// backend/config/reliability_experiments.py, with which it shares names.
//
// Two sources switch a name on:
//  - the account's remote flags (services/experiments/reliability_flags.dart), in every build;
//  - a local selection (a compile-time define or a file in the app's Documents directory), only in
//    a debug build or a `local_dev` profile build. A released build ignores both.
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'package:omi/services/experiments/reliability_flags.dart';

class ReliabilityExperiments {
  ReliabilityExperiments._();

  /// Selects every registered experiment.
  static const all = 'all';

  /// Optional file in the app's Documents directory: comma or newline
  /// separated names. When present it replaces the compile-time selection; an
  /// empty file selects nothing. Read only where [localSelectionAllowed].
  static const fileName = 'reliability_experiments.txt';

  /// `--dart-define=OMI_RELIABILITY_EXPERIMENTS=name,other` (or `all`).
  static const compileTimeValue = String.fromEnvironment('OMI_RELIABILITY_EXPERIMENTS');

  /// A local selection applies to a debug build and to a `local_dev` profile build (the build a
  /// developer installs against a local stack, which has no flag snapshot). Never to a released build.
  static const localSelectionAllowed = kDebugMode || String.fromEnvironment('OMI_APP_PROFILE') == 'local_dev';

  /// name -> what turning it on changes. Register here before using a name.
  static const Map<String, String> registered = {
    'receipt_long_poll': 'While foregrounded, one open receipts-wait request (waitForSyncReceipts) reports finished '
        'upload jobs; those jobs leave the per-job GET polling. Off: GET polling only, the endpoint is never called.',
    'receipt_check_during_drain': 'While one upload or drain is in flight, accepted jobs are status-checked every '
        '20 s. Off: no status check until the drain ends.',
    'status_fetch_failure_isolated': 'An exception from one job status GET becomes a transient (or throttled) '
        'result and the pass continues. Off: the exception ends the reconcile pass.',
    'keep_cooldown_after_upload': 'A successful upload clears the rate-limit state only when no cooldown is active. '
        'Off: it clears unless the cooldown reason is an edge throttle.',
    'end_open_conversation': 'Every way of ending a conversation (End Conversation, Finish, Wrap Up, the record '
        'button\'s stop, a pendant double-tap) seals the speech file the phone is still writing, so it uploads in '
        'the normal order instead of running to its 60 s cap, and sends the moment of the End with the request '
        '(X-Omi-Ended-At). Off: the open file is left to its own rules and no End time is sent.',
    'fast_end_feedback': 'After a conversation is ended (End Conversation, Finish, Wrap Up, the record button\'s '
        'stop or a pendant double-tap), two waiting requests (waitForConversationSummary) return it the moment it is '
        'committed with its outline and the moment its summary is stored; Home, the open conversation page and the '
        'processing page apply each answer. Off: they learn of both from their existing polls, and the endpoint is '
        'never called. No layout change.',
    'end_button_by_device': 'End Conversation also shows on the account\'s open conversation when the server says '
        'its latest speech came from this app install (v3_capture_device_id on the live read equals this phone\'s '
        'own device id), whatever the listening connection carries; Finish, Wrap Up and the record button\'s stop '
        'then name that conversation too. Off: only the listening session\'s own recording or lines decide.',
    'instant_live_text': 'The phone\'s own speech recognition shows at once. (1) The open conversation\'s '
        'Transcript also shows the "Live on this phone" lines when the server says its latest speech came from '
        'this app install (v3_capture_device_id), whatever the listening connection carries. (2) After a '
        'conversation is ended, Home\'s Listening row comes back as soon as the recogniser hears words spoken '
        'after that End. (3) The open conversation\'s page reports its transcript as on screen to the listening '
        'connection while this phone feeds that conversation, as the Listening page does, so the server streams a '
        'batch-only session from the moment the page opens; the lines it sends back show under the transcript '
        'until the conversation holds them. Off: the lines show only when the listening session\'s recording is a '
        'source of the conversation, the Listening row stays hidden until the next conversation arrives or two '
        'minutes pass, and the open conversation\'s page never reports.',
    'vendor_recognizer_on_opened_app': 'Live words do not depend on one recogniser. While capture is active and '
        'the app is in front, (1) the phone\'s own speech recogniser runs whether or not the server granted the '
        'on-phone preview (audio routing and the local_preview declaration are unchanged), (2) a copy of the audio '
        'from the capture taps goes on a separate display-only connection (/v4/live-words) to the vendor recogniser, '
        'on every screen, with the last 3 s sent first, and (3) every screen that shows the phone\'s live words shows '
        'one merged list: the phone\'s own lines, plus the vendor\'s words only for stretches where the phone\'s '
        'recogniser returned nothing. The connection closes when the app leaves the front or capture is paused or '
        'stopped. A recogniser that claims to stream while the vendor hears about 10 s of speech is restarted, at most '
        'once in 3 minutes. Home\'s Listening row comes back on merged words spoken after an End; coming to the '
        'front and opening the Listening page seal the phone file being written. Nothing is stored: batch stays the '
        'transcript. Off: the recogniser starts only on the server\'s grant and no display connection is opened.',
    'phone_recogniser_mute': 'Test only. The phone\'s own speech recogniser runs as usual and its results are '
        'dropped before display, so the vendor words of vendor_recognizer_on_opened_app can be seen on a phone '
        'whose recogniser works. Off: its results show.',
    'early_title_icon': 'An ended conversation shows its title and emoji on Home as soon as the server has fixed '
        'them (title_locked, set when it is committed with its outline), seconds before its summary. Home\'s list '
        'takes such a row while its status is still processing, so it replaces the "Processing…" row; with '
        'fast_end_feedback the outline answer hands it over at once. Its tile shows the emoji, and the line under '
        'the title keeps saying Transcribing… or Writing summary… until the summary is stored. Off: Home lists only '
        'completed rows, so "Processing…" stays until the summary is stored, and a tile in the pipeline shows a '
        'spinner or a pen.',
  };

  static Set<String> _selected = localSelectionAllowed ? parse(compileTimeValue) : const {};
  static Set<String>? _override;
  static bool Function(String name) _remote = ReliabilityFlags.enabled;

  /// Names currently selected, including `all` and names this build does not know.
  static Set<String> get selected => Set.unmodifiable(_override ?? _selected);

  /// Selected names no code reads: a typo would otherwise silently run the baseline.
  static Set<String> get unknown => selected.where((name) => name != all && !registered.containsKey(name)).toSet();

  static bool enabled(String name) {
    if (!registered.containsKey(name)) {
      throw ArgumentError.value(name, 'name', 'Unregistered reliability experiment');
    }
    final names = _override ?? _selected;
    if (names.contains(name) || names.contains(all)) return true;
    // A test's selection is exact; otherwise the account's remote flag decides.
    return _override == null && _remote(name);
  }

  static Set<String> parse(String text) =>
      text.split(RegExp(r'[,\r\n]')).map((item) => item.trim()).where((item) => item.isNotEmpty).toSet();

  /// Reads the local selection once at start-up. Never throws: any failure leaves
  /// the compile-time selection in place. A released build reads nothing and returns at once.
  static Future<void> load({
    Future<Directory> Function() documentsDirectory = getApplicationDocumentsDirectory,
    String compileTime = compileTimeValue,
    bool allowed = localSelectionAllowed,
  }) async {
    if (!allowed) {
      _selected = const {};
      return;
    }
    var names = <String>{};
    try {
      names = parse(compileTime);
      final file = await (() async {
        final candidate = File('${(await documentsDirectory()).path}/$fileName');
        return await candidate.exists() ? await candidate.readAsString() : null;
      })()
          .timeout(const Duration(seconds: 2));
      if (file != null) names = parse(file);
    } catch (error) {
      debugPrint('ReliabilityExperiments: selection file unavailable: ${error.runtimeType}');
    }
    _selected = names;
    final unread = unknown;
    if (unread.isNotEmpty) debugPrint('ReliabilityExperiments: unknown names ignored: ${unread.join(', ')}');
  }

  /// Replaces the remote flag read in a test; `null` restores the account's flags.
  @visibleForTesting
  static void remoteForTesting(bool Function(String name)? read) => _remote = read ?? ReliabilityFlags.enabled;

  /// Replaces the selection in a test; `null` restores the loaded one.
  @visibleForTesting
  static void overrideForTesting(Set<String>? names) {
    for (final name in names ?? const <String>{}) {
      if (name != all && !registered.containsKey(name)) {
        throw ArgumentError.value(name, 'names', 'Unregistered reliability experiment');
      }
    }
    _override = names == null ? null : Set.of(names);
  }
}
