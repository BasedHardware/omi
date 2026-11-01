import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/experiments/home_redesign.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    HomeRedesign.resetForTesting();
  });

  Future<void> read(String? variant, {String uid = 'u1', String? who = 'd1'}) => HomeRedesign.refresh(
        readVariant: (_) async => variant,
        identity: () => who,
        uid: uid,
        identityWait: Duration.zero,
      );

  test('today\'s Home until PostHog assigns the test arm', () async {
    HomeRedesign.loadSaved(uid: 'u1');
    expect(HomeRedesign.on, isFalse);
    await read(null);
    expect(HomeRedesign.on, isFalse, reason: 'an unread flag is control');
    await read('test');
    expect(HomeRedesign.on, isTrue);
  });

  test('control and unknown variants show today\'s Home', () async {
    await read('control');
    expect(HomeRedesign.on, isFalse);
    await read('surprise');
    expect(HomeRedesign.on, isFalse);
  });

  test('the arm is saved per account and applied at the next start without a read', () async {
    await read('test', uid: 'u1');
    HomeRedesign.resetForTesting();
    HomeRedesign.loadSaved(uid: 'u1');
    expect(HomeRedesign.on, isTrue);
    HomeRedesign.loadSaved(uid: 'someone-else');
    expect(HomeRedesign.on, isFalse, reason: 'another account has its own arm');
  });

  test('never switches a Home already on screen; the new arm waits for the next launch', () async {
    HomeRedesign.loadSaved(uid: 'u1');
    HomeRedesign.markHomeShown(record: (_, __) => true);
    await read('test');
    expect(HomeRedesign.on, isFalse);
    HomeRedesign.resetForTesting();
    HomeRedesign.loadSaved(uid: 'u1');
    expect(HomeRedesign.on, isTrue);
  });

  test('exposure is sent for the arm on screen, only once PostHog has assigned one', () async {
    final exposures = <String>[];
    bool record(String key, String variant) {
      exposures.add('$key=$variant');
      return true;
    }

    SharedPreferencesUtil().uid = 'u1';
    HomeRedesign.loadSaved(uid: 'u1');
    HomeRedesign.markHomeShown(record: record);
    expect(exposures, isEmpty, reason: 'no assignment yet');

    await read('test');
    HomeRedesign.resetForTesting();
    HomeRedesign.loadSaved(uid: 'u1');
    HomeRedesign.markHomeShown(record: record);
    expect(exposures, ['home-redesign=test']);
  });

  test('no identity yet: nothing is read or saved', () async {
    var reads = 0;
    await HomeRedesign.refresh(
      readVariant: (_) async {
        reads++;
        return 'test';
      },
      identity: () => null,
      uid: 'u1',
      identityWait: Duration.zero,
    );
    expect(reads, 0);
    expect(HomeRedesign.on, isFalse);
  });
}
