import 'package:flutter_test/flutter_test.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';

void main() {
  group('display models', () {
    test('DisplayState maps cleanly to and from ints', () {
      expect(DisplayState.fromInt(0), DisplayState.starting);
      expect(DisplayState.fromInt(1), DisplayState.started);
      expect(DisplayState.fromInt(2), DisplayState.stopping);
      expect(DisplayState.fromInt(3), DisplayState.stopped);
      expect(DisplayState.fromInt(null), DisplayState.stopped);
      expect(DisplayState.started.value, 1);
    });

    test('DisplayPlaybackEventType round-trips through the wire token', () {
      expect(
        DisplayPlaybackEventType.fromWire('ended'),
        DisplayPlaybackEventType.ended,
      );
      expect(
        DisplayPlaybackEventType.fromWire('bogus'),
        DisplayPlaybackEventType.unknown,
      );
      final event = DisplayPlaybackEvent.fromMap(<Object?, Object?>{
        'event': 'stopped',
      });
      expect(event.type, DisplayPlaybackEventType.stopped);
    });

    test('leaf nodes serialize without callbacks', () {
      expect(
        const DisplayText('Hi', style: DisplayTextStyle.heading).toJson(),
        <String, Object?>{
          'type': 'text',
          'text': 'Hi',
          'style': 'heading',
        },
      );
      expect(
        const DisplayImage(
          'https://x/y.png',
          sizePreset: DisplayImageSize.fill,
          cornerRadius: DisplayCornerRadius.medium,
        ).toJson(),
        <String, Object?>{
          'type': 'image',
          'uri': 'https://x/y.png',
          'sizePreset': 'fill',
          'cornerRadius': 'medium',
        },
      );
      expect(
        const DisplayIcon(DisplayIconName.videoCamera).toJson(),
        <String, Object?>{'type': 'icon', 'iconName': 'videoCamera'},
      );
    });

    test('FlexBox serializes its modifiers and nested children', () {
      const tree = FlexBox(
        direction: DisplayDirection.row,
        spacing: 12,
        padding: 24,
        background: FlexBoxBackground.card,
        alignment: DisplayAlignment.center,
        crossAlignment: DisplayAlignment.center,
        flexGrow: 7,
        children: [
          DisplayText('Title', style: DisplayTextStyle.body),
        ],
      );
      final json = tree.toJson();
      expect(json['type'], 'flexBox');
      expect(json['direction'], 'row');
      expect(json['spacing'], 12);
      expect(json['padding'], 24);
      expect(json['background'], 'card');
      expect(json['alignment'], 'center');
      expect(json['crossAlignment'], 'center');
      expect(json['flexGrow'], 7);
      final children = json['children']! as List<Object?>;
      expect(children, hasLength(1));
      expect((children.first! as Map)['text'], 'Title');
    });

    test('callbacks are registered with ids and dispatched by id', () {
      var tapped = false;
      var clicked = false;
      DisplayPlaybackEvent? playback;

      final tree = FlexBox(
        onTap: () => tapped = true,
        children: [
          DisplayButton(label: 'Go', onClick: () => clicked = true),
          VideoPlayer(
            'https://x/v.mp4',
            onPlaybackEvent: (e) => playback = e,
          ),
        ],
      );

      final table = DisplayCallbackTable();
      final json = tree.toJson(table);
      expect(table.length, 3);

      final onTapId = json['onTapId']! as String;
      final children = json['children']! as List<Object?>;
      final buttonId = (children[0]! as Map)['onClickId']! as String;
      final videoId = (children[1]! as Map)['onPlaybackEventId']! as String;

      table
        ..dispatch(<Object?, Object?>{'callbackId': onTapId, 'type': 'tap'})
        ..dispatch(<Object?, Object?>{'callbackId': buttonId})
        ..dispatch(<Object?, Object?>{
          'callbackId': videoId,
          'type': 'playback',
          'event': 'ended',
        });

      expect(tapped, isTrue);
      expect(clicked, isTrue);
      expect(playback?.type, DisplayPlaybackEventType.ended);
    });

    test('toJson without a table omits callback ids', () {
      final json = FlexBox(onTap: () {}).toJson();
      expect(json.containsKey('onTapId'), isFalse);
    });
  });
}
