// Shared components hold their shape at every phone size and text size (the layout lint's
// findings, 2026-09-26): a settings title keeps its line beside a long value, a section title keeps
// its line beside its buttons, and centred state copy breaks evenly.
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/ui.dart';

import '../../support/real_fonts.dart';
import 'ui_test_app.dart';

void main() {
  const widths = [320.0, 360.0, 375.0, 393.0, 440.0];

  // Real fonts, not the test font's square glyphs, so widths are real.
  setUpAll(loadRealFonts);

  Future<void> at(WidgetTester tester, double width, Widget child, {double scale = 1}) async {
    tester.view.physicalSize = Size(width, 900);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = scale;
    addTearDown(tester.view.reset);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await pumpUi(tester, Scaffold(body: SingleChildScrollView(padding: const EdgeInsets.all(20), child: child)));
  }

  double oneLine(WidgetTester tester, String text) {
    final paragraph = tester.renderObject<RenderParagraph>(find.text(text));
    return paragraph.getMaxIntrinsicHeight(double.infinity);
  }

  testWidgets('a short title keeps its line beside a long value; the value gives way', (tester) async {
    for (final width in widths) {
      await at(
        tester,
        width,
        const OmiSettingsGroup(children: [
          OmiSettingsRow(
            leading: Icon(Icons.volume_up),
            title: 'Voice Response',
            value: 'Only when I ask with my voice',
            onTap: _noop,
          ),
        ]),
      );
      expect(tester.getSize(find.text('Voice Response')).height, oneLine(tester, 'Voice Response'),
          reason: 'title on one line at $width');
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('a section title keeps its line; its buttons drop under it when both do not fit', (tester) async {
    for (final width in widths) {
      await at(
        tester,
        width,
        const OmiSectionHeader(
          'Developer API',
          trailing: Wrap(spacing: 8, runSpacing: 8, children: [
            OmiButton.secondary(label: 'Docs', size: OmiButtonSize.compact, onPressed: _noop),
            OmiButton.secondary(label: 'Create Key', size: OmiButtonSize.compact, onPressed: _noop),
          ]),
        ),
        scale: 1.3,
      );
      expect(tester.getSize(find.text('Developer API')).height, oneLine(tester, 'Developer API'),
          reason: 'title on one line at $width');
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('centred state copy never leaves one word alone', (tester) async {
    for (final width in widths) {
      await at(
        tester,
        width,
        const OmiErrorState(message: 'Please check your connection and try again'),
        scale: 1.3,
      );
      final paragraph = tester.renderObject<RenderParagraph>(find.text('Please check your connection and try again'));
      final lines = (paragraph.size.height / oneLine(tester, 'Please check your connection and try again')).round();
      if (lines > 1) {
        final boxes = paragraph.getBoxesForSelection(
            const TextSelection(baseOffset: 0, extentOffset: 'Please check your connection and try again'.length));
        final lastTop = boxes.map((b) => b.top).reduce((a, b) => a > b ? a : b);
        final lastLine =
            boxes.where((b) => (b.top - lastTop).abs() < 1).fold<double>(0, (w, b) => w + b.right - b.left);
        expect(lastLine, greaterThan(paragraph.size.width * 0.4), reason: 'an even last line at $width');
      }
      expect(tester.takeException(), isNull);
    }
  });
}

void _noop() {}
