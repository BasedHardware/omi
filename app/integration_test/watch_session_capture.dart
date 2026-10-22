// Native UI fixture: production rows/navigation with synthetic saved recordings.
// No account, microphone, real recording or backend is used by this target.
import 'package:flutter/material.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/local_recording_group.dart';
import 'package:omi/pages/conversations/widgets/conversations_group_widget.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class _SavedRecordings extends ChangeNotifier implements LocalRecordingsProvider {
  _SavedRecordings() {
    const session = '0123456789abcdef0123456789abcdef';
    final start = DateTime(2026, 10, 21, 15, 4).millisecondsSinceEpoch ~/ 1000;
    recordings = List.generate(40, (index) {
      final time = start + index * 60;
      final name = 'audio_omibatchwatch${session}s${index}_pcm16_16000_1_fs160_$time.bin';
      return LocalRecording(
        fileName: name,
        filePath: '/synthetic/$name',
        timerStart: time,
        codec: BleAudioCodec.pcm16,
        frameSize: 160,
        sizeBytes: 1944000,
        seconds: 60,
        state: LocalRecordingState.pending,
      );
    });
    homeRecordings = groupLocalRecordings(recordings);
  }

  @override
  late final List<LocalRecording> recordings;
  @override
  late final List<LocalRecordingGroup> homeRecordings;
  String? _playing;
  @override
  bool isPlaying(LocalRecording recording) => _playing == recording.id;
  @override
  bool canPlay(LocalRecording recording) => true;
  @override
  LocalRecording? getById(String id) => recordings.where((r) => r.id == id).firstOrNull;
  @override
  Future<List<double>?> getWaveform(LocalRecording recording) async => null;
  @override
  Future<void> togglePlayback(LocalRecording recording) async {
    _playing = isPlaying(recording) ? null : recording.id;
    notifyListeners();
  }

  @override
  bool get isProcessingAudio => false;
  @override
  bool get isPreparingShare => false;
  @override
  Duration get totalDuration => const Duration(minutes: 1);
  @override
  Duration get currentPosition => Duration.zero;
  @override
  double get playbackProgress => 0;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> main() async {
  MarionetteBinding.ensureInitialized();
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  OmiColors.active = OmiColors.forBrightness(Brightness.dark);
  final provider = _SavedRecordings();
  runApp(ChangeNotifierProvider<LocalRecordingsProvider>.value(
    value: provider,
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildOmiTheme(brightness: Brightness.dark),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(
          builder: (context) => Scaffold(
                appBar: AppBar(title: Text(context.l10n.home)),
                body: SingleChildScrollView(
                    child: ConversationsGroupWidget(
                        conversations: const [],
                        recordings: provider.recordings,
                        date: DateTime(2026, 10, 21),
                        isFirst: true)),
              )),
    ),
  ));
}
