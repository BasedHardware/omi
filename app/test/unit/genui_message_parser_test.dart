import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/chat/widgets/genui_message_parser.dart';

void main() {
  test('parses fenced genui payload and returns remaining markdown', () {
    const raw = '''
Here is the nearest place.

```genui
{"type":"location_result","title":"Nearest convenience store","description":"7-Eleven within 200m","latitude":37.0,"longitude":-122.0,"actions":[{"type":"open_map","label":"Open map"}]}
```
''';

    final parsed = parseGenUiMessage(raw);

    expect(parsed.markdownText, 'Here is the nearest place.');
    expect(parsed.card, isNotNull);
    expect(parsed.card!.type, GenUiCardType.locationResult);
    expect(parsed.card!.title, 'Nearest convenience store');
    expect(parsed.card!.actions.single.type, GenUiActionType.openMap);
  });

  test('returns plain markdown when payload is invalid', () {
    const raw = '```genui\nnot-json\n```';

    final parsed = parseGenUiMessage(raw);

    expect(parsed.card, isNull);
    expect(parsed.markdownText, raw);
  });

  test('parses location request action', () {
    const raw = '```genui\n{"type":"location_request","title":"Share your location","actions":[{"type":"share_location","label":"Share location"}]}\n```';

    final parsed = parseGenUiMessage(raw);

    expect(parsed.card, isNotNull);
    expect(parsed.card!.type, GenUiCardType.locationRequest);
    expect(parsed.card!.actions.single.type, GenUiActionType.shareLocation);
  });

  test('adds default action for location request without explicit actions', () {
    const raw = '```genui\n{"type":"location_request"}\n```';

    final parsed = parseGenUiMessage(raw);

    expect(parsed.card, isNotNull);
    expect(parsed.card!.title, 'Share your location');
    expect(parsed.card!.actions.single.type, GenUiActionType.shareLocation);
  });

  test('parses nested coordinates and adds open map action', () {
    const raw = '''
```genui
{"type":"location_result","location":{"lat":"37.77","lng":"-122.42"}}
```
''';

    final parsed = parseGenUiMessage(raw);

    expect(parsed.card, isNotNull);
    expect(parsed.card!.latitude, 37.77);
    expect(parsed.card!.longitude, -122.42);
    expect(parsed.card!.actions.single.type, GenUiActionType.openMap);
  });
}
