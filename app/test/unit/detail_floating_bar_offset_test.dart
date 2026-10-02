import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/conversation_detail/page.dart';

void main() {
  test('the conversation bar rests at 32pt and never sinks under a taller system bar', () {
    // No inset (older Android, iPhone SE) and the 34pt iPhone home indicator
    // keep the resting position within 2pt.
    expect(detailFloatingBarBottom(0), 32);
    expect(detailFloatingBarBottom(24), 32);
    expect(detailFloatingBarBottom(34), 34);
    // Android 16, 3-button navigation: the bar sits on top of it, not under it.
    expect(detailFloatingBarBottom(48), 48);
  });
}
