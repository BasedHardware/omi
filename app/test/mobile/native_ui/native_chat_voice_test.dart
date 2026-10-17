import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_chat_voice.dart';
import 'package:omi/providers/voice_recorder_provider.dart';

class _Voice extends ChangeNotifier implements VoiceRecorderProvider {
  _Voice(this.state);
  @override
  final VoiceRecorderState state;
  final commands = <String>[];
  @override
  bool get isRecording => state == VoiceRecorderState.recording;
  @override
  List<double> get audioLevels => [.1, double.nan, 3];
  @override
  Future<void> processRecording() async => commands.add('process');
  @override
  Future<void> discardRecording() async => commands.add('discard');
  @override
  Future<void> retry() async => commands.add('retry');
  @override
  void requestAutoSendOnNextTranscript() => commands.add('autoSend');
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  Future<List<NativeRow>> project(WidgetTester tester, _Voice voice) async {
    late List<NativeRow> rows;
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Builder(builder: (context) {
        rows = nativeVoiceRows(context, voice);
        return const SizedBox();
      }),
    ));
    return rows;
  }

  testWidgets('native Send requests auto-send before invoking the existing transcription owner', (tester) async {
    final voice = _Voice(VoiceRecorderState.recording);
    final rows = await project(tester, voice);
    expect(rows.every((row) => row.valid), true);
    await rows.singleWhere((row) => row.id == 'chat_voice_send').action!(null);
    expect(voice.commands, ['autoSend', 'process']);
    await rows.singleWhere((row) => row.id == 'chat_voice_discard').action!(null);
    expect(voice.commands.last, 'discard');
  });
  for (final state in [VoiceRecorderState.pendingRecovery, VoiceRecorderState.transcribeFailed]) {
    testWidgets('native $state keeps the existing recovery commands', (tester) async {
      final voice = _Voice(state);
      final rows = await project(tester, voice);
      expect(rows.any((row) => row.id == 'chat_voice_send'), false);
      await rows.singleWhere((row) => row.id == 'chat_voice_retry').action!(null);
      expect(voice.commands, ['retry']);
    });
  }
}
