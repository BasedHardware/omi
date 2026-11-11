// Standalone native screenshot fixture for the reported first voice prompt. Run with
// flutter run --release --flavor prod -t integration_test/onboarding_header_capture.dart.
// Uses the production page and host layout with inert I/O, without signing in or resetting data.
import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:path_provider/path_provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_step_layout.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/ui/ui.dart';

void main() {
  if (kDebugMode) {
    MarionetteBinding.ensureInitialized();
  } else {
    WidgetsFlutterBinding.ensureInitialized();
  }
  runApp(const _CaptureApp());
}

class _CaptureApp extends StatefulWidget {
  const _CaptureApp();

  @override
  State<_CaptureApp> createState() => _CaptureAppState();
}

class _CaptureAppState extends State<_CaptureApp> {
  final _surface = GlobalKey();
  final _flow = GuidedVoiceController(_InertVoiceIO());
  bool _fixed = false;

  @override
  void initState() {
    super.initState();
    unawaited(_capture());
  }

  Future<void> _capture() async {
    final storage =
        Platform.isAndroid ? (await getExternalStorageDirectory())! : await getApplicationDocumentsDirectory();
    final directory = Directory('${storage.path}/omi-layout-evidence');
    await directory.create(recursive: true);
    for (final fixed in [false, true]) {
      if (!mounted) return;
      setState(() => _fixed = fixed);
      await Future<void>.delayed(const Duration(seconds: 3));
      await WidgetsBinding.instance.endOfFrame;
      final boundary = _surface.currentContext!.findRenderObject()! as RenderRepaintBoundary;
      final screenshot = await boundary.toImage(pixelRatio: 2);
      final bytes = await screenshot.toByteData(format: ui.ImageByteFormat.png);
      final platform = Platform.isIOS ? 'ios' : 'android';
      final side = fixed ? 'after' : 'before';
      await File('${directory.path}/$platform-$side.png').writeAsBytes(bytes!.buffer.asUint8List());
      screenshot.dispose();
      debugPrint('ONBOARDING_CAPTURE $platform-$side saved');
    }
  }

  @override
  void dispose() {
    _flow.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildOmiTheme(brightness: Brightness.light),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: RepaintBoundary(
          key: _surface,
          child: Scaffold(
            body: OnboardingStepLayout(
              reserveHeader: _fixed,
              progress: const OnboardingProgressDots(current: 4, total: 6),
              onBack: () {},
              child: SpeechProfileWidget(controller: _flow, goNext: () {}, onSkip: () {}),
            ),
          ),
        ),
      );
}

class _InertVoiceIO implements GuidedVoiceIO {
  @override
  bool get livePreview => false;
  @override
  Future<void> prepare() async {}
  @override
  Future<void> start(void Function(Uint8List) onAudio, VoidCallback onInterrupted) async {}
  @override
  Future<void> stop() async {}
  @override
  Future<String> transcribe(Uint8List pcm) async => '';
  @override
  Future<bool> enroll(Uint8List pcm) async => false;
  @override
  Future<bool> remember(String text) async => false;
  @override
  Future<bool> saveGoal(String text, String idempotencyKey) async => false;
  @override
  Future<void> close() async {}
}
