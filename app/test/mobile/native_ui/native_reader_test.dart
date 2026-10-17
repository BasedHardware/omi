import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_rich_text.dart';

void main() {
  test('playback positions are finite wall seconds within the current audio span', () async {
    final seeks = <Object?>[];
    final slider =
        NativeRow('position', 'Recordings', kind: 'slider', value: 0.0, maximumValue: 120, action: seeks.add);
    expect(slider.valid, true);
    for (final value in ['12', true, double.nan, double.infinity, -1, 121]) {
      await expectLater(
          dispatchNativeAction(MethodCall('action', {'id': 'position', 'value': value}),
              isActive: () => true, rows: [slider]),
          throwsA(isA<PlatformException>()));
    }
    await dispatchNativeAction(const MethodCall('action', {'id': 'position', 'value': 95.5}),
        isActive: () => true, rows: [slider]);
    expect(seeks, [95.5]);
    expect(const NativeRow('position', 'Audio', kind: 'slider', value: 0.0, maximumValue: 0).valid, false);
  });

  test('reader follows and scrolls only ids in the current transcript', () {
    const sections = [
      NativeSection('transcript', [NativeRow('segment:1', 'Words', kind: 'transcript')])
    ];
    const reader = NativeReader(
        currentId: 'segment:1',
        targetId: 'segment:1',
        scroll: NativeRow('scroll', 'Transcript', kind: 'menu', options: {'segment:1': 'Words', 'suspend': 'Suspend'}));
    expect(reader.validFor(sections), true);
    expect(reader.validFor(const []), false);
    expect(const NativeReader(targetId: 'foreign').validFor(sections), false);
    expect(const NativeReader(request: -1).validFor(sections), false);
    expect(
        const NativeReader(scroll: NativeRow('scroll', 'Reader', kind: 'menu', options: {'foreign': 'Words'}))
            .validFor(sections),
        false);
  });

  test('feedback visibility does not claim exposure while hidden or after session expiry', () async {
    var visible = false;
    var submitted = 0;
    final row = NativeRow('feedback', 'Helpful?',
        kind: 'label', onVisible: (_) => visible = true, onHidden: (_) => visible = false);
    final save = NativeRow('save', 'Submit', action: (_) => submitted++);
    await dispatchNativeAction(const MethodCall('action', {'id': '_visible:feedback'}),
        isActive: () => true, rows: [row, save]);
    expect(visible, true);
    await dispatchNativeAction(const MethodCall('action', {'id': '_hidden:feedback'}),
        isActive: () => true, rows: [row, save]);
    expect(visible, false);
    await expectLater(
        dispatchNativeAction(const MethodCall('action', {'id': '_visible:feedback'}),
            isActive: () => false, rows: [row]),
        throwsA(isA<PlatformException>()));
    expect(visible, false);
    expect(submitted, 0);
  });

  test('rich notes keep headed lists, links, code, images and table cells', () {
    final blocks = nativeRichText(
        '## Decisions\n\n1. **Ship** [notes](https://example.com).\n   - Keep *the owner*.\n\n> Quote\n\n```swift\nlet value = 1\n```\n\n| Key | Value |\n| --- | --- |\n| Mode | Native |\n\n![Screenshot](https://example.com/image.jpg)');
    expect(blocks.first, containsPair('kind', 'heading'));
    expect(blocks.first['level'], 2);
    expect(blocks.any((block) => block['prefix'] == '1.' && (block['text'] as String).contains('**Ship**')), true);
    expect(blocks.any((block) => block['indent'] == 1 && block['prefix'] == '•'), true);
    expect(blocks.any((block) => block['kind'] == 'quote'), true);
    expect(blocks.firstWhere((block) => block['kind'] == 'code')['text'], contains('let value = 1'));
    expect(blocks.firstWhere((block) => block['kind'] == 'table')['cells'], [
      ['Key', 'Value'],
      ['Mode', 'Native']
    ]);
    expect(blocks.firstWhere((block) => block['kind'] == 'image')['uri'], 'https://example.com/image.jpg');
    expect(NativeRow('note', 'Note', kind: 'rich_text', blocks: blocks).valid, true);
  });
  test('Markdown task states and list images remain present in the reader', () {
    final blocks = nativeRichText('- [x] Finished\n- [ ] Pending\n- ![Evidence](https://example.com/image.png)');
    expect(blocks.any((block) => (block['text'] as String).contains('☑')), true);
    expect(blocks.any((block) => (block['text'] as String).contains('☐')), true);
    expect(blocks.any((block) => block['kind'] == 'image' && block['uri'] == 'https://example.com/image.png'), true);
  });
}
