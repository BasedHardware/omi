import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';

const _empty = {'nodes': <dynamic>[], 'edges': <dynamic>[]};
const _populated = {
  'nodes': [
    {'id': 'entity', 'label': 'Hiking'}
  ],
  'edges': <dynamic>[]
};

void main() {
  late HttpServer server;
  late List<String> requests;

  setUpAll(() async {
    Env.init(_Env());
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await PlatformManager.initializeServices();
  });

  setUp(() async {
    AuthService.installLocalHarnessTokenGateway(_TokenGateway('onboarding-user'));
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    Env.overrideApiBaseUrl('http://${server.address.host}:${server.port}/');
    requests = [];
  });

  tearDown(() async {
    await server.close(force: true);
    Env.clearApiBaseUrlOverride();
  });

  // Real orchestration, session guards, parsing and HTTP dispatch; loopback only.
  void serve(void Function(HttpRequest) respond) {
    server.listen((request) async {
      requests.add('${request.method} ${request.uri.path}');
      if (request.method == 'POST') {
        expect(await utf8.decoder.bind(request).join(), '{}');
        // A regression finishes quickly instead of entering the polling loop.
        request.response.statusCode = HttpStatus.conflict;
      }
      respond(request);
      await request.response.close();
    });
  }

  for (final status in [HttpStatus.gatewayTimeout, HttpStatus.forbidden]) {
    test('failed compatibility read $status cannot trigger a rebuild', () async {
      serve((request) {
        if (request.method == 'GET') request.response.statusCode = status;
      });
      await expectLater(KnowledgeGraphApi.prebuildForOnboarding(), throwsException);
      expect(requests, ['GET /v1/knowledge-graph']);
    });
  }

  test('malformed compatibility response cannot trigger a rebuild', () async {
    serve((request) {
      if (request.method == 'GET') request.response.write('not-json');
    });
    await expectLater(KnowledgeGraphApi.prebuildForOnboarding(), throwsFormatException);
    expect(requests, ['GET /v1/knowledge-graph']);
  });

  for (final status in [HttpStatus.serviceUnavailable, HttpStatus.forbidden]) {
    test('failed canonical read $status cannot trigger a legacy rebuild', () async {
      serve((request) {
        if (request.uri.path.endsWith('/canonical')) {
          request.response.statusCode = status;
        } else if (request.method == 'GET') {
          request.response.write(jsonEncode(_empty));
        }
      });
      await expectLater(KnowledgeGraphApi.prebuildForOnboarding(), throwsException);
      expect(requests, ['GET /v1/knowledge-graph', 'GET /v1/knowledge-graph/canonical']);
    });
  }

  test('account replacement during a canonical read cannot rebuild for the new account', () async {
    serve((request) {
      request.response.write(jsonEncode(_empty));
      if (request.uri.path.endsWith('/canonical')) {
        AuthService.installLocalHarnessTokenGateway(_TokenGateway('replacement-user'));
      }
    });
    await expectLater(KnowledgeGraphApi.prebuildForOnboarding(), throwsA(isA<KnowledgeGraphSessionChanged>()));
    expect(requests, ['GET /v1/knowledge-graph', 'GET /v1/knowledge-graph/canonical']);
  });

  for (final catalog in [
    <Map<String, String>>[],
    [
      {'id': 'memory:1', 'label': 'I enjoy hiking'}
    ]
  ]) {
    test('canonical read with ${catalog.length} catalog memories never rebuilds or polls', () async {
      serve((request) => request.response.write(jsonEncode({
            ..._empty,
            if (request.uri.path.endsWith('/canonical')) ...{'catalog_nodes': catalog, 'has_more': false},
          })));
      await KnowledgeGraphApi.prebuildForOnboarding();
      expect(requests, ['GET /v1/knowledge-graph', 'GET /v1/knowledge-graph/canonical']);
    });
  }

  test('working compatibility graph does not request canonical recovery or rebuild', () async {
    serve((request) => request.response.write(jsonEncode(_populated)));
    await KnowledgeGraphApi.prebuildForOnboarding();
    expect(requests, ['GET /v1/knowledge-graph']);
  });

  for (final status in [HttpStatus.notFound, HttpStatus.serviceUnavailable]) {
    test('positively absent canonical state $status permits legacy rebuild, then 409 stops polling', () async {
      serve((request) {
        if (request.uri.path.endsWith('/canonical')) {
          request.response.statusCode = status;
          if (status == HttpStatus.serviceUnavailable) {
            request.response.headers.set('x-omi-knowledge-graph-state', 'unestablished');
          }
        } else if (request.method == 'GET') {
          request.response.write(jsonEncode(_empty));
        }
      });
      await KnowledgeGraphApi.prebuildForOnboarding();
      expect(requests, [
        'GET /v1/knowledge-graph',
        'GET /v1/knowledge-graph/canonical',
        'POST /v1/knowledge-graph/rebuild',
      ]);
    });
  }

  test('queued legacy rebuild retains bounded stability polling', () async {
    var queued = false;
    serve((request) {
      if (request.uri.path.endsWith('/canonical')) {
        request.response.statusCode = HttpStatus.notFound;
      } else if (request.method == 'POST') {
        queued = true;
        request.response.statusCode = HttpStatus.ok;
        request.response.write(jsonEncode({'nodes_count': 0, 'edges_count': 0, 'status': 'queued'}));
      } else {
        request.response.write(jsonEncode(queued ? _populated : _empty));
      }
    });
    await KnowledgeGraphApi.prebuildForOnboarding();
    expect(requests, [
      'GET /v1/knowledge-graph',
      'GET /v1/knowledge-graph/canonical',
      'POST /v1/knowledge-graph/rebuild',
      'GET /v1/knowledge-graph',
      'GET /v1/knowledge-graph',
    ]);
  });

  test('failed legacy rebuild propagates without polling', () async {
    serve((request) {
      if (request.uri.path.endsWith('/canonical')) {
        request.response.statusCode = HttpStatus.notFound;
      } else if (request.method == 'POST') {
        request.response.statusCode = HttpStatus.badRequest;
      } else {
        request.response.write(jsonEncode(_empty));
      }
    });
    await expectLater(KnowledgeGraphApi.prebuildForOnboarding(), throwsException);
    expect(requests, [
      'GET /v1/knowledge-graph',
      'GET /v1/knowledge-graph/canonical',
      'POST /v1/knowledge-graph/rebuild',
    ]);
  });
}

class _TokenGateway implements AuthTokenGateway {
  _TokenGateway(this.uid);
  final String uid;
  @override
  AuthUserSnapshot get currentUser => AuthUserSnapshot(uid: uid);
  @override
  Future<RefreshedAuthToken?> forceRefresh() async =>
      RefreshedAuthToken(token: 'loopback-only', expirationTime: DateTime.now().add(const Duration(hours: 1)));
  @override
  Future<void> signOut() async {}
}

class _Env implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.test.invalid/';
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}
