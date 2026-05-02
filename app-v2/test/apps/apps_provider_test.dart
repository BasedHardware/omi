import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:nooto_v2/apps/apps_provider.dart';
import 'package:nooto_v2/apps/apps_storage.dart';
import 'package:nooto_v2/services/api_client.dart';

ApiClient _client(MockClient mock) => ApiClient(
  httpClient: mock,
  getIdToken: ({bool forceRefresh = false}) async => 'tok',
  signOut: () async {},
  baseUrl: 'https://example.test/',
);

/// Records every launch-url invocation so tests can assert the URL the
/// provider built (target + ?uid=…). Always returns true — the provider
/// only cares about throw-vs-return, not the bool.
class _RecordingLauncher {
  final List<Uri> calls = [];
  LaunchMode? lastMode;
  bool throwOnLaunch = false;

  Future<bool> launch(Uri uri, {LaunchMode mode = LaunchMode.platformDefault}) async {
    if (throwOnLaunch) {
      throw Exception('Safari unavailable');
    }
    calls.add(uri);
    lastMode = mode;
    return true;
  }
}

Map<String, dynamic> _sampleCatalog({bool includeAuthSteps = false}) => {
  'groups': [
    {
      'capability': {'id': 'popular', 'title': 'Popular'},
      'data': [
        {
          'id': 'a1',
          'name': 'Alpha',
          'description': 'First app',
          'image': 'https://x/a1.png',
          'enabled': true,
          'installs': 42,
          'capabilities': ['chat'],
        },
        {
          'id': 'a2',
          'name': 'Beta',
          'description': 'Second app',
          'image': '',
          'enabled': false,
          'installs': 7,
          'capabilities': const [],
        },
      ],
    },
    {
      'capability': {'id': 'integrations', 'title': 'Integrations'},
      'data': [
        {
          'id': 'jira',
          'name': 'Jira',
          'description': 'Sync tickets',
          'image': 'https://x/jira.png',
          'enabled': false,
          'installs': 12,
          'capabilities': ['integration'],
          if (includeAuthSteps)
            'external_integration': {
              'auth_steps': [
                {'name': 'Connect Jira', 'url': 'https://jira.test/oauth/start'},
              ],
              'app_home_url': 'https://jira.test/home',
            },
        },
      ],
    },
    {
      // Empty groups should be dropped — backend can include them.
      'capability': {'id': 'empty', 'title': 'Empty'},
      'data': const [],
    },
  ],
  'meta': {'capabilities': const [], 'groupCount': 2, 'limit': 20, 'offset': 0},
};

/// Routes both /v2/apps and /v1/apps/enabled. enabledList is the user's
/// installed-set returned for /v1/apps/enabled.
MockClient _routedMock({List<String> enabledList = const [], bool includeAuthSteps = false}) {
  return MockClient((req) async {
    if (req.url.path == '/v2/apps') {
      return http.Response(jsonEncode(_sampleCatalog(includeAuthSteps: includeAuthSteps)), 200);
    }
    if (req.url.path == '/v1/apps/enabled') {
      return http.Response(jsonEncode(enabledList), 200);
    }
    if (req.url.path == '/v1/apps/enable') {
      return http.Response('{"status":"ok"}', 200);
    }
    if (req.url.path == '/v1/apps/disable') {
      return http.Response('{"status":"ok"}', 200);
    }
    return http.Response('not found', 404);
  });
}

void main() {
  late Directory tempDir;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    tempDir = await Directory.systemTemp.createTemp('apps_provider_test');
    Hive.init(tempDir.path);
  });

  setUp(() async {
    if (!Hive.isBoxOpen(AppsBoxes.prefs)) {
      await Hive.openBox<Map>(AppsBoxes.prefs);
    }
    await Hive.box<Map>(AppsBoxes.prefs).clear();
  });

  tearDownAll(() async {
    await Hive.deleteFromDisk();
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  test('load() hydrates groups, drops empty, marks enabled from /v1/apps/enabled', () async {
    final provider = AppsProvider(client: _client(_routedMock(enabledList: ['a1', 'jira'])));

    await provider.load();

    expect(provider.groups, hasLength(2));
    expect(provider.isEnabled('a1'), isTrue);
    expect(provider.isEnabled('a2'), isFalse);
    expect(provider.isEnabled('jira'), isTrue);
    expect(provider.error, isNull);
  });

  test('load() is idempotent — second call no-ops without force', () async {
    var hits = 0;
    final mock = MockClient((req) async {
      hits += 1;
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode(_sampleCatalog()), 200);
      }
      return http.Response('[]', 200);
    });
    final provider = AppsProvider(client: _client(mock));

    await provider.load();
    await provider.load();
    await provider.load();

    // 2 hits per load (catalog + enabled); 1 load total => 2 hits.
    expect(hits, 2);
  });

  test('load() captures error on 500', () async {
    final mock = MockClient((req) async => http.Response('boom', 500));
    final provider = AppsProvider(client: _client(mock));

    await provider.load();

    expect(provider.error, isNotNull);
    expect(provider.groups, isEmpty);
  });

  test('install() optimistically marks enabled and posts to backend', () async {
    String? capturedPath;
    String? capturedQuery;
    final mock = MockClient((req) async {
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode(_sampleCatalog()), 200);
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response('[]', 200);
      }
      if (req.url.path == '/v1/apps/enable') {
        capturedPath = req.url.path;
        capturedQuery = req.url.query;
        return http.Response('{"status":"ok"}', 200);
      }
      return http.Response('not found', 404);
    });
    final launcher = _RecordingLauncher();
    final provider = AppsProvider(client: _client(mock), launchUrl: launcher.launch, getUid: () async => 'test-uid');
    await provider.load();
    expect(provider.isEnabled('a1'), isFalse);

    final ok = await provider.install('a1');

    expect(ok, isTrue);
    expect(capturedPath, '/v1/apps/enable');
    expect(capturedQuery, contains('app_id=a1'));
    expect(provider.isEnabled('a1'), isTrue);
    // REGRESSION: 200-path install must NOT touch the system browser. Apps
    // without `external_integration` should never trigger an OAuth round-trip.
    expect(launcher.calls, isEmpty);
  });

  test('install() rolls back local state on backend error', () async {
    final mock = MockClient((req) async {
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode(_sampleCatalog()), 200);
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response('[]', 200);
      }
      if (req.url.path == '/v1/apps/enable') {
        return http.Response('boom', 500);
      }
      return http.Response('not found', 404);
    });
    final provider = AppsProvider(client: _client(mock));
    await provider.load();

    final ok = await provider.install('a1');

    expect(ok, isFalse);
    expect(provider.isEnabled('a1'), isFalse);
    expect(provider.error, isNotNull);
  });

  test('uninstall() flips state off and posts disable', () async {
    String? capturedPath;
    final mock = MockClient((req) async {
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode(_sampleCatalog()), 200);
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response(jsonEncode(['a1']), 200);
      }
      if (req.url.path == '/v1/apps/disable') {
        capturedPath = req.url.path;
        return http.Response('{"status":"ok"}', 200);
      }
      return http.Response('not found', 404);
    });
    final provider = AppsProvider(client: _client(mock));
    await provider.load();
    expect(provider.isEnabled('a1'), isTrue);

    final ok = await provider.uninstall('a1');

    expect(ok, isTrue);
    expect(capturedPath, '/v1/apps/disable');
    expect(provider.isEnabled('a1'), isFalse);
  });

  test('install() no-ops if already installed', () async {
    var hitEnable = 0;
    final mock = MockClient((req) async {
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode(_sampleCatalog()), 200);
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response(jsonEncode(['a1']), 200);
      }
      if (req.url.path == '/v1/apps/enable') {
        hitEnable += 1;
        return http.Response('{"status":"ok"}', 200);
      }
      return http.Response('not found', 404);
    });
    final provider = AppsProvider(client: _client(mock));
    await provider.load();

    final ok = await provider.install('a1');

    expect(ok, isFalse);
    expect(hitEnable, 0);
  });

  group('OAuth install flow', () {
    test(
      'install() with auth_steps + 400 "App setup is not completed" opens browser and keeps optimistic enable',
      () async {
        final mock = MockClient((req) async {
          if (req.url.path == '/v2/apps') {
            return http.Response(jsonEncode(_sampleCatalog(includeAuthSteps: true)), 200);
          }
          if (req.url.path == '/v1/apps/enabled') {
            return http.Response('[]', 200);
          }
          if (req.url.path == '/v1/apps/enable') {
            return http.Response(jsonEncode({'detail': 'App setup is not completed'}), 400);
          }
          return http.Response('not found', 404);
        });
        final launcher = _RecordingLauncher();
        final provider = AppsProvider(
          client: _client(mock),
          launchUrl: launcher.launch,
          getUid: () async => 'test-uid',
        );
        await provider.load();

        final ok = await provider.install('jira');

        // OAuth in flight — caller is told "not actually done yet".
        expect(ok, isFalse);
        // Optimistic enable STAYS in place across the OAuth round-trip; the
        // deep-link callback retries enable when the plugin redirects back.
        expect(provider.isEnabled('jira'), isTrue);
        expect(provider.error, isNull);
        // Browser was opened with auth_steps[0].url + ?uid=test-uid.
        expect(launcher.calls, hasLength(1));
        expect(launcher.calls.single.toString(), 'https://jira.test/oauth/start?uid=test-uid');
        expect(launcher.lastMode, LaunchMode.externalApplication);
      },
    );

    test('install() with 400 + other detail rolls back enable and surfaces error', () async {
      final mock = MockClient((req) async {
        if (req.url.path == '/v2/apps') {
          return http.Response(jsonEncode(_sampleCatalog(includeAuthSteps: true)), 200);
        }
        if (req.url.path == '/v1/apps/enabled') {
          return http.Response('[]', 200);
        }
        if (req.url.path == '/v1/apps/enable') {
          return http.Response(jsonEncode({'detail': 'Some other reason'}), 400);
        }
        return http.Response('not found', 404);
      });
      final launcher = _RecordingLauncher();
      final provider = AppsProvider(client: _client(mock), launchUrl: launcher.launch, getUid: () async => 'test-uid');
      await provider.load();

      final ok = await provider.install('jira');

      expect(ok, isFalse);
      expect(provider.isEnabled('jira'), isFalse);
      expect(provider.error, isNotNull);
      expect(launcher.calls, isEmpty);
    });

    test('install() with 500 rolls back enable and surfaces error', () async {
      final mock = MockClient((req) async {
        if (req.url.path == '/v2/apps') {
          return http.Response(jsonEncode(_sampleCatalog(includeAuthSteps: true)), 200);
        }
        if (req.url.path == '/v1/apps/enabled') {
          return http.Response('[]', 200);
        }
        if (req.url.path == '/v1/apps/enable') {
          return http.Response('boom', 500);
        }
        return http.Response('not found', 404);
      });
      final launcher = _RecordingLauncher();
      final provider = AppsProvider(client: _client(mock), launchUrl: launcher.launch, getUid: () async => 'test-uid');
      await provider.load();

      final ok = await provider.install('jira');

      expect(ok, isFalse);
      expect(provider.isEnabled('jira'), isFalse);
      expect(provider.error, isNotNull);
      expect(launcher.calls, isEmpty);
    });
  });

  group('handleSetupComplete', () {
    test('on success, reloads apps and retries install when not yet enabled', () async {
      var enableHits = 0;
      var enabledList = <String>[];
      final mock = MockClient((req) async {
        if (req.url.path == '/v2/apps') {
          return http.Response(jsonEncode(_sampleCatalog(includeAuthSteps: true)), 200);
        }
        if (req.url.path == '/v1/apps/enabled') {
          return http.Response(jsonEncode(enabledList), 200);
        }
        if (req.url.path == '/v1/apps/enable') {
          enableHits += 1;
          return http.Response('{"status":"ok"}', 200);
        }
        return http.Response('not found', 404);
      });
      final launcher = _RecordingLauncher();
      final provider = AppsProvider(client: _client(mock), launchUrl: launcher.launch, getUid: () async => 'test-uid');
      await provider.load();
      // Server still reports jira as not enabled (plugin hasn't flipped it
      // server-side yet). After OAuth redirect, the provider should retry.
      enabledList = const [];

      await provider.handleSetupComplete('jira', 'success');

      // Reload happens regardless — fresh enabled state from the server.
      // Then install() retries because !_enabledIds.contains(jira).
      expect(enableHits, 1);
      expect(provider.isEnabled('jira'), isTrue);
    });

    test('on success, skips retry if server already reports app enabled', () async {
      var enableHits = 0;
      final mock = MockClient((req) async {
        if (req.url.path == '/v2/apps') {
          return http.Response(jsonEncode(_sampleCatalog(includeAuthSteps: true)), 200);
        }
        if (req.url.path == '/v1/apps/enabled') {
          return http.Response(jsonEncode(['jira']), 200);
        }
        if (req.url.path == '/v1/apps/enable') {
          enableHits += 1;
          return http.Response('{"status":"ok"}', 200);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(
        client: _client(mock),
        launchUrl: _RecordingLauncher().launch,
        getUid: () async => 'test-uid',
      );
      await provider.load();

      await provider.handleSetupComplete('jira', 'success');

      // Server already reports jira enabled — no retry needed.
      expect(enableHits, 0);
      expect(provider.isEnabled('jira'), isTrue);
    });

    test('on error status, rolls back optimistic enable and surfaces error, no retry', () async {
      var enableHits = 0;
      // Install returns 400-needs-setup so the provider takes the OAuth
      // branch and leaves the optimistic enable in place — exactly the state
      // we'd be in mid-OAuth when the user cancels.
      final mock = MockClient((req) async {
        if (req.url.path == '/v2/apps') {
          return http.Response(jsonEncode(_sampleCatalog(includeAuthSteps: true)), 200);
        }
        if (req.url.path == '/v1/apps/enabled') {
          return http.Response('[]', 200);
        }
        if (req.url.path == '/v1/apps/enable') {
          enableHits += 1;
          return http.Response(jsonEncode({'detail': 'App setup is not completed'}), 400);
        }
        return http.Response('not found', 404);
      });
      final launcher = _RecordingLauncher();
      final provider = AppsProvider(client: _client(mock), launchUrl: launcher.launch, getUid: () async => 'test-uid');
      await provider.load();
      await provider.install('jira'); // OAuth in flight, optimistic enable kept.
      expect(provider.isEnabled('jira'), isTrue);
      final enableHitsBefore = enableHits;

      await provider.handleSetupComplete('jira', 'user_cancelled');

      expect(provider.error, contains('OAuth failed'));
      expect(provider.isEnabled('jira'), isFalse);
      // No retry on error — only the reload's GETs hit the wire, no new POST.
      expect(enableHits, enableHitsBefore);
    });

    test('on success for unknown app id, reloads but skips retry', () async {
      var loadHits = 0;
      var enableHits = 0;
      final mock = MockClient((req) async {
        if (req.url.path == '/v2/apps') {
          loadHits += 1;
          return http.Response(jsonEncode(_sampleCatalog()), 200);
        }
        if (req.url.path == '/v1/apps/enabled') {
          return http.Response('[]', 200);
        }
        if (req.url.path == '/v1/apps/enable') {
          enableHits += 1;
          return http.Response('{"status":"ok"}', 200);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(
        client: _client(mock),
        launchUrl: _RecordingLauncher().launch,
        getUid: () async => 'test-uid',
      );
      await provider.load();
      final loadHitsBefore = loadHits;

      await provider.handleSetupComplete('not-a-real-app', 'success');

      // load(force:true) ran exactly once.
      expect(loadHits, loadHitsBefore + 1);
      // No install retry — app isn't in our local catalog.
      expect(enableHits, 0);
    });
  });

  group('Two-way sync state', () {
    test('isTwoWaySyncEnabled returns false by default for any app id', () async {
      final provider = AppsProvider(client: _client(_routedMock()));

      expect(provider.isTwoWaySyncEnabled('jira'), isFalse);
      expect(provider.isTwoWaySyncEnabled('anything'), isFalse);
      expect(provider.isTwoWaySyncEnabled(''), isFalse);
    });

    test('setTwoWaySync flips value, notifies, and persists across rebuilds', () async {
      final provider = AppsProvider(client: _client(_routedMock()));
      var notifyCount = 0;
      provider.addListener(() => notifyCount += 1);

      await provider.setTwoWaySync('jira', true);

      expect(provider.isTwoWaySyncEnabled('jira'), isTrue);
      expect(notifyCount, greaterThanOrEqualTo(1));

      // New provider sees the persisted value via Hive hydration.
      final reborn = AppsProvider(client: _client(_routedMock()));
      expect(reborn.isTwoWaySyncEnabled('jira'), isTrue);
      expect(reborn.isTwoWaySyncEnabled('linear'), isFalse);

      // Toggle back off and confirm persistence again.
      await reborn.setTwoWaySync('jira', false);
      final third = AppsProvider(client: _client(_routedMock()));
      expect(third.isTwoWaySyncEnabled('jira'), isFalse);
    });
  });

  group('Two-way sync server reconciliation', () {
    test('setTwoWaySync(nooto-jira, true) PATCHes /v1/integrations/nooto-jira/prefs', () async {
      String? capturedPath;
      String? capturedBody;
      String? capturedMethod;
      final mock = MockClient((req) async {
        if (req.url.path == '/v1/integrations/nooto-jira/prefs') {
          capturedPath = req.url.path;
          capturedMethod = req.method;
          capturedBody = req.body;
          return http.Response(jsonEncode({'two_way_sync_enabled': true}), 200);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));

      await provider.setTwoWaySync('nooto-jira', true);
      // Allow the unawaited best-effort PATCH to settle.
      await Future<void>.delayed(const Duration(milliseconds: 10));

      expect(capturedMethod, 'PATCH');
      expect(capturedPath, '/v1/integrations/nooto-jira/prefs');
      expect(capturedBody, contains('"two_way_sync_enabled":true'));
      expect(provider.isTwoWaySyncEnabled('nooto-jira'), isTrue);
    });

    test('setTwoWaySync server failure does NOT roll back local state', () async {
      final mock = MockClient((req) async {
        if (req.url.path == '/v1/integrations/nooto-jira/prefs') {
          return http.Response('boom', 500);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));

      await provider.setTwoWaySync('nooto-jira', true);
      await Future<void>.delayed(const Duration(milliseconds: 10));

      // Hive is the source of truth on-device — a failed PATCH must not
      // flip the local value back. Cross-device reconcile happens on
      // next load().
      expect(provider.isTwoWaySyncEnabled('nooto-jira'), isTrue);
    });

    test('setTwoWaySync skips server call for unmapped app ids', () async {
      var integrationHits = 0;
      final mock = MockClient((req) async {
        if (req.url.path.startsWith('/v1/integrations/')) {
          integrationHits += 1;
          return http.Response(jsonEncode({'two_way_sync_enabled': true}), 200);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));

      await provider.setTwoWaySync('some-other-app', true);
      await Future<void>.delayed(const Duration(milliseconds: 10));

      // No server call — unmapped app id has no integration_id mapping.
      expect(integrationHits, 0);
      expect(provider.isTwoWaySyncEnabled('some-other-app'), isTrue);
    });

    test('load() reconciles server pref into Hive when Jira is installed', () async {
      // Server says ON, local Hive has nothing → after load() local is ON.
      final mock = MockClient((req) async {
        if (req.url.path == '/v2/apps') {
          return http.Response(jsonEncode(_sampleCatalog()), 200);
        }
        if (req.url.path == '/v1/apps/enabled') {
          return http.Response(jsonEncode(['nooto-jira']), 200);
        }
        if (req.url.path == '/v1/integrations/nooto-jira/prefs') {
          return http.Response(jsonEncode({'two_way_sync_enabled': true}), 200);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));

      expect(provider.isTwoWaySyncEnabled('nooto-jira'), isFalse);
      await provider.load();

      expect(provider.isTwoWaySyncEnabled('nooto-jira'), isTrue);
    });

    test('load() reconcile defaults to OFF when server returns null/missing', () async {
      // Local was previously ON via Hive; server returns null/missing
      // pref → server wins → local flips back to OFF.
      // (Two-way-sync default OFF is a hard product rule.)
      await Hive.box<Map>(AppsBoxes.prefs).put('twoWaySync', {'nooto-jira': true});

      final mock = MockClient((req) async {
        if (req.url.path == '/v2/apps') {
          return http.Response(jsonEncode(_sampleCatalog()), 200);
        }
        if (req.url.path == '/v1/apps/enabled') {
          return http.Response(jsonEncode(['nooto-jira']), 200);
        }
        if (req.url.path == '/v1/integrations/nooto-jira/prefs') {
          // No `two_way_sync_enabled` key in body → defaults to false.
          return http.Response(jsonEncode({}), 200);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));
      // Hydrate from Hive happens in constructor.
      expect(provider.isTwoWaySyncEnabled('nooto-jira'), isTrue);

      await provider.load();

      expect(provider.isTwoWaySyncEnabled('nooto-jira'), isFalse);
    });

    test('load() skips reconcile for non-installed apps', () async {
      var prefsHits = 0;
      final mock = MockClient((req) async {
        if (req.url.path == '/v2/apps') {
          return http.Response(jsonEncode(_sampleCatalog()), 200);
        }
        if (req.url.path == '/v1/apps/enabled') {
          return http.Response(jsonEncode(['some-other-app']), 200);
        }
        if (req.url.path == '/v1/integrations/nooto-jira/prefs') {
          prefsHits += 1;
          return http.Response(jsonEncode({'two_way_sync_enabled': true}), 200);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));

      await provider.load();

      // No reconcile because nooto-jira isn't installed.
      expect(prefsHits, 0);
    });

    test('load() reconcile failure does not surface as load error', () async {
      final mock = MockClient((req) async {
        if (req.url.path == '/v2/apps') {
          return http.Response(jsonEncode(_sampleCatalog()), 200);
        }
        if (req.url.path == '/v1/apps/enabled') {
          return http.Response(jsonEncode(['nooto-jira']), 200);
        }
        if (req.url.path == '/v1/integrations/nooto-jira/prefs') {
          return http.Response('boom', 500);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));

      await provider.load();

      // Catalog loaded normally; pref reconcile failure is swallowed.
      expect(provider.error, isNull);
      expect(provider.groups, isNotEmpty);
    });

    test('load() populates lastSyncedAt from prefs response', () async {
      // Server returns a stamped last_synced_at; the provider parses it
      // into a DateTime so the UI can render "Last synced: 2 min ago".
      final mock = MockClient((req) async {
        if (req.url.path == '/v2/apps') {
          return http.Response(jsonEncode(_sampleCatalog()), 200);
        }
        if (req.url.path == '/v1/apps/enabled') {
          return http.Response(jsonEncode(['nooto-jira']), 200);
        }
        if (req.url.path == '/v1/integrations/nooto-jira/prefs') {
          return http.Response(
            jsonEncode({'two_way_sync_enabled': false, 'last_synced_at': '2026-05-01T12:34:56+00:00'}),
            200,
          );
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));
      expect(provider.lastSyncedAt('nooto-jira'), isNull);

      await provider.load();

      final ts = provider.lastSyncedAt('nooto-jira');
      expect(ts, isNotNull);
      expect(ts!.toUtc().toIso8601String(), '2026-05-01T12:34:56.000Z');
    });
  });

  group('syncNow', () {
    test('200 path returns null and updates lastSyncedAt + lastSyncCount', () async {
      String? capturedPath;
      String? capturedMethod;
      final mock = MockClient((req) async {
        if (req.url.path == '/v1/integrations/nooto-jira/sync-now') {
          capturedPath = req.url.path;
          capturedMethod = req.method;
          return http.Response(
            jsonEncode({'synced': 3, 'errors': 0, 'last_synced_at': '2026-05-01T12:00:00+00:00'}),
            200,
          );
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));

      final result = await provider.syncNow('nooto-jira');

      expect(result, isNull);
      expect(capturedMethod, 'POST');
      expect(capturedPath, '/v1/integrations/nooto-jira/sync-now');
      expect(provider.lastSyncCount('nooto-jira'), 3);
      expect(provider.lastSyncedAt('nooto-jira')!.toUtc().toIso8601String(), '2026-05-01T12:00:00.000Z');
      expect(provider.isSyncing('nooto-jira'), isFalse);
    });

    test('400 jira_not_installed maps to "not_installed"', () async {
      final mock = MockClient((req) async {
        if (req.url.path == '/v1/integrations/nooto-jira/sync-now') {
          return http.Response(jsonEncode({'detail': 'jira_not_installed'}), 400);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));

      final result = await provider.syncNow('nooto-jira');

      expect(result, 'not_installed');
      expect(provider.isSyncing('nooto-jira'), isFalse);
    });

    test('502 jira_plugin_error maps to "plugin_error"', () async {
      final mock = MockClient((req) async {
        if (req.url.path == '/v1/integrations/nooto-jira/sync-now') {
          return http.Response(jsonEncode({'detail': 'jira_plugin_error'}), 502);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));

      final result = await provider.syncNow('nooto-jira');

      expect(result, 'plugin_error');
    });

    test('500 / other ApiError maps to "network"', () async {
      final mock = MockClient((req) async {
        if (req.url.path == '/v1/integrations/nooto-jira/sync-now') {
          return http.Response('boom', 500);
        }
        return http.Response('not found', 404);
      });
      final provider = AppsProvider(client: _client(mock));

      final result = await provider.syncNow('nooto-jira');

      expect(result, 'network');
    });

    test('transport exception maps to "network"', () async {
      final mock = MockClient((req) async {
        throw const SocketLikeException('offline');
      });
      final provider = AppsProvider(client: _client(mock));

      final result = await provider.syncNow('nooto-jira');

      expect(result, 'network');
    });

    test('unmapped app id returns "not_supported" without hitting the wire', () async {
      var hits = 0;
      final mock = MockClient((req) async {
        hits += 1;
        return http.Response('{}', 200);
      });
      final provider = AppsProvider(client: _client(mock));

      final result = await provider.syncNow('linear-or-something');

      expect(result, 'not_supported');
      expect(hits, 0);
    });

    test('isSyncing flips true mid-call and back to false on completion', () async {
      // Hold the response until the test releases it so we can observe
      // the isSyncing transition mid-flight.
      final completer = Completer<http.Response>();
      final mock = MockClient((req) async => completer.future);
      final provider = AppsProvider(client: _client(mock));

      final transitions = <bool>[];
      provider.addListener(() => transitions.add(provider.isSyncing('nooto-jira')));

      final future = provider.syncNow('nooto-jira');
      // Yield once so the provider's first notifyListeners (set isSyncing
      // = true) dispatches. The await on _client.post hands control back.
      await Future<void>.delayed(Duration.zero);
      expect(provider.isSyncing('nooto-jira'), isTrue);

      completer.complete(
        http.Response(jsonEncode({'synced': 0, 'errors': 0, 'last_synced_at': '2026-05-01T00:00:00Z'}), 200),
      );
      await future;

      expect(provider.isSyncing('nooto-jira'), isFalse);
      // We expect at least one true transition followed by a false one.
      expect(transitions, contains(true));
      expect(transitions.last, isFalse);
    });

    test('concurrent calls for same appId no-op the second one', () async {
      var hits = 0;
      final completer = Completer<http.Response>();
      final mock = MockClient((req) async {
        hits += 1;
        return completer.future;
      });
      final provider = AppsProvider(client: _client(mock));

      final first = provider.syncNow('nooto-jira');
      // Yield so the first call dispatches its POST and isSyncing flips
      // true. Without this, we'd race the second call ahead of the first.
      await Future<void>.delayed(Duration.zero);
      expect(provider.isSyncing('nooto-jira'), isTrue);

      final second = await provider.syncNow('nooto-jira');

      // Second call returned null without making a new request; first
      // call hasn't completed yet.
      expect(second, isNull);
      expect(hits, 1);

      completer.complete(
        http.Response(jsonEncode({'synced': 1, 'errors': 0, 'last_synced_at': '2026-05-01T00:00:00Z'}), 200),
      );
      await first;
    });
  });
}

/// Simulates a transport-level failure (the http MockClient handler throws
/// rather than returning a Response). ApiClient should surface this as a
/// generic exception, which AppsProvider.syncNow collapses to "network".
class SocketLikeException implements Exception {
  const SocketLikeException(this.message);
  final String message;
  @override
  String toString() => 'SocketLikeException($message)';
}
