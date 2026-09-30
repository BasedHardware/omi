// Synthetic meeting screenshots for the visual audit: a video call, a slide, an editor and a doc,
// drawn at runtime so no binary fixture (and no real person's screen) enters the repository.
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/painting.dart';

const _w = 1280.0;
const _h = 800.0;

void _text(Canvas c, String text, Offset at,
    {double size = 22,
    Color color = const Color(0xFFFFFFFF),
    FontWeight weight = FontWeight.w400,
    double maxWidth = 900}) {
  final builder = ui.ParagraphBuilder(ui.ParagraphStyle(fontFamily: 'Roboto', fontSize: size, fontWeight: weight))
    ..pushStyle(ui.TextStyle(color: color))
    ..addText(text);
  final p = builder.build()..layout(ui.ParagraphConstraints(width: maxWidth));
  c.drawParagraph(p, at);
}

RRect _rr(double x, double y, double w, double h, double r) => RRect.fromLTRBR(x, y, x + w, y + h, Radius.circular(r));

void _videoCall(Canvas c) {
  c.drawRect(const Rect.fromLTWH(0, 0, _w, _h), Paint()..color = const Color(0xFF202124));
  const people = [
    ('Maya Chen', Color(0xFF3B5B7A), 'MC'),
    ('Jonas Weber', Color(0xFF5E4B7A), 'JW'),
    ('Priya Natarajan', Color(0xFF3F6B55), 'PN'),
    ('You', Color(0xFF7A5A3B), 'YO'),
  ];
  const tileW = 610.0, tileH = 330.0;
  for (var i = 0; i < people.length; i++) {
    final x = 20.0 + (i % 2) * (tileW + 20);
    final y = 20.0 + (i ~/ 2) * (tileH + 20);
    final (name, color, initials) = people[i];
    c.drawRRect(_rr(x, y, tileW, tileH, 14), Paint()..color = const Color(0xFF3C4043));
    c.drawCircle(Offset(x + tileW / 2, y + tileH / 2 - 10), 64, Paint()..color = color);
    _text(c, initials, Offset(x + tileW / 2 - 34, y + tileH / 2 - 40), size: 48, weight: FontWeight.w500);
    _text(c, name, Offset(x + 18, y + tileH - 42), size: 22, weight: FontWeight.w500);
    if (i == 0) {
      c.drawRRect(
          _rr(x, y, tileW, tileH, 14),
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 4
            ..color = const Color(0xFF8AB4F8));
    }
  }
  // Control bar.
  for (var i = 0; i < 5; i++) {
    final color = i == 4 ? const Color(0xFFEA4335) : const Color(0xFF3C4043);
    c.drawRRect(_rr(420 + i * 90.0, 720, i == 4 ? 100 : 64, 56, 28), Paint()..color = color);
  }
  _text(c, '10:32 | Weekly product sync', const Offset(24, 736), size: 20, color: const Color(0xFFE8EAED));
}

void _slide(Canvas c) {
  c.drawRect(const Rect.fromLTWH(0, 0, _w, _h), Paint()..color = const Color(0xFFF4F1EA));
  c.drawRect(const Rect.fromLTWH(0, 0, 18, _h), Paint()..color = const Color(0xFFD9653B));
  _text(c, 'Q4 onboarding roadmap', const Offset(90, 90),
      size: 56, color: const Color(0xFF1F1F1F), weight: FontWeight.w700);
  const bullets = [
    'Week 1 — simplify the first recording',
    'Week 3 — memories you can find again',
    'Week 5 — share notes with one tap',
    'Week 8 — measure activation at day 7',
  ];
  for (var i = 0; i < bullets.length; i++) {
    c.drawCircle(Offset(104, 250.0 + i * 90), 8, Paint()..color = const Color(0xFFD9653B));
    _text(c, bullets[i], Offset(130, 232.0 + i * 90), size: 32, color: const Color(0xFF333333));
  }
  c.drawRRect(_rr(860, 560, 340, 180, 16), Paint()..color = const Color(0xFFE6DFD1));
  for (var i = 0; i < 5; i++) {
    final h = 30.0 + i * 24;
    c.drawRect(Rect.fromLTWH(900.0 + i * 58, 720 - h, 36, h), Paint()..color = const Color(0xFF3B6E8F));
  }
}

void _editor(Canvas c) {
  c.drawRect(const Rect.fromLTWH(0, 0, _w, _h), Paint()..color = const Color(0xFF1E1E1E));
  c.drawRect(const Rect.fromLTWH(0, 0, 240, _h), Paint()..color = const Color(0xFF252526));
  c.drawRect(const Rect.fromLTWH(240, 0, _w - 240, 44), Paint()..color = const Color(0xFF2D2D2D));
  _text(c, 'onboarding_flow.dart', const Offset(262, 10), size: 18, color: const Color(0xFFCCCCCC));
  for (var i = 0; i < 9; i++) {
    _text(c, ['lib', 'pages', 'onboarding', 'widgets', 'services', 'test', 'pubspec.yaml', 'README.md', 'l10n'][i],
        Offset(28, 70.0 + i * 34),
        size: 17, color: const Color(0xFFBBBBBB));
  }
  const lines = [
    ('class OnboardingFlow extends StatefulWidget {', Color(0xFF569CD6)),
    ('  const OnboardingFlow({super.key});', Color(0xFFDCDCAA)),
    ('', Color(0xFFFFFFFF)),
    ('  // Step one records before it asks for anything.', Color(0xFF6A9955)),
    ('  Future<void> startFirstRecording() async {', Color(0xFFDCDCAA)),
    ("    await recorder.start(mode: 'stream');", Color(0xFFCE9178)),
    ('    analytics.track(OnboardingStep.recording);', Color(0xFF9CDCFE)),
    ('  }', Color(0xFFD4D4D4)),
    ('}', Color(0xFFD4D4D4)),
  ];
  for (var i = 0; i < lines.length; i++) {
    _text(c, '${i + 12}', Offset(262, 80.0 + i * 40), size: 20, color: const Color(0xFF858585));
    _text(c, lines[i].$1, Offset(320, 80.0 + i * 40), size: 22, color: lines[i].$2);
  }
}

void _doc(Canvas c) {
  c.drawRect(const Rect.fromLTWH(0, 0, _w, _h), Paint()..color = const Color(0xFFE9ECEF));
  c.drawRect(const Rect.fromLTWH(0, 0, _w, 60), Paint()..color = const Color(0xFFFFFFFF));
  c.drawRRect(_rr(200, 12, 880, 36, 18), Paint()..color = const Color(0xFFF1F3F4));
  _text(c, 'docs.example.com/launch-checklist', const Offset(230, 19), size: 18, color: const Color(0xFF5F6368));
  c.drawRect(const Rect.fromLTWH(240, 90, 800, 710), Paint()..color = const Color(0xFFFFFFFF));
  _text(c, 'Launch checklist', const Offset(300, 140),
      size: 44, color: const Color(0xFF202124), weight: FontWeight.w700);
  const items = [
    'Release notes drafted',
    'Support macros updated',
    'Rollout at 10%, then 50%',
    'Dashboard alert owners'
  ];
  for (var i = 0; i < items.length; i++) {
    c.drawRRect(
        _rr(300, 238.0 + i * 70, 26, 26, 5),
        Paint()
          ..style = i < 2 ? PaintingStyle.fill : PaintingStyle.stroke
          ..strokeWidth = 2
          ..color = const Color(0xFF1A73E8));
    _text(c, items[i], Offset(346, 236.0 + i * 70), size: 26, color: const Color(0xFF3C4043));
  }
}

/// PNG bytes for each synthetic frame, keyed by the file name the fixture backend serves.
Future<Map<String, Uint8List>> renderScreenFrameFixtures() async {
  final painters = <String, void Function(Canvas)>{
    'call.png': _videoCall,
    'slide.png': _slide,
    'editor.png': _editor,
    'doc.png': _doc,
  };
  final out = <String, Uint8List>{};
  for (final entry in painters.entries) {
    final recorder = ui.PictureRecorder();
    entry.value(Canvas(recorder));
    final image = await recorder.endRecording().toImage(_w.toInt(), _h.toInt());
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    image.dispose();
    out[entry.key] = data!.buffer.asUint8List();
  }
  return out;
}

/// One frame of a `ConversationScreenFrameSet`, in wire shape.
Map<String, dynamic> screenFrameJson(String baseUrl, String id, String image,
        {required String role, required int rank, required String caption, String? badge}) =>
    {
      'id': id,
      'captured_at': '2026-09-30T10:${(10 + rank * 7).toString().padLeft(2, '0')}:00Z',
      'role': role,
      'rank': rank,
      'caption': caption,
      'labels': <String>[],
      'source_badge': badge,
      'focal_region': null,
      'width': _w.toInt(),
      'height': _h.toInt(),
      'content_url': '${baseUrl}fixture-images/$image',
      'thumbnail_url': '${baseUrl}fixture-images/$image',
      'url_expires_at': DateTime.now().toUtc().add(const Duration(minutes: 60)).toIso8601String(),
      'ground': {
        'stops': ['#3B5B7A', '#202124'],
        'is_neutral': false
      },
    };
