import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import '../support/spine/contract.dart';

class FakeApiAuth implements AuthService {
  FakeApiAuth(this.result, this.events);
  final AuthTokenResult result;
  final List<String> events;
  final expired = <AuthSessionExpiredEvent>[];
  String token = 'old-fixture-token';
  @override
  Future<AuthTokenResult> refreshIdToken() async {
    events.add('refresh');
    if (result case AuthTokenSuccess(token: final refreshedToken)) token = refreshedToken;
    return result;
  }

  @override
  Future<void> expireSession(AuthSessionExpiredEvent event) async {
    expired.add(event);
  }

  @override
  void recordAuthenticatedRequest401({required bool recovered, required String outcome}) {
    events.add('record:$recovered:$outcome');
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Uninjected auth operation: ${invocation.memberName}');
}

void main() {
  for (final mode in ['recovered', 'transient', 'terminal', 'rejected-again']) {
    contractTest('C3 production request execution preserves 401 refresh/replay: $mode', () async {
      pendingContract('C3');
      final events = <String>[];
      final auth = FakeApiAuth(
          mode == 'transient'
              ? const AuthTokenTransientFailure(failureClass: 'network')
              : mode == 'terminal'
                  ? const AuthTokenTerminalFailure(code: 'user-disabled')
                  : const AuthTokenSuccess(token: 'new-fixture-token', expirationTime: null),
          events);
      var sends = 0;
      var decodes = 0;
      final execution = ApiExecutionSeams(
          auth: auth,
          headers: (request) async {
            events.add('headers');
            return {...request.headers, 'Authorization': 'Bearer ${auth.token}'};
          },
          transport: (request) async {
            sends++;
            expect(request.url, 'http://127.0.0.1:1/conversations');
            expect(request.method, 'POST');
            expect(request.body, 'fixture-body');
            expect(request.headers['X-Fixture'], 'preserved');
            final expected = sends == 1 ? 'old-fixture-token' : 'new-fixture-token';
            expect(request.headers['Authorization'], 'Bearer $expected');
            events.add('send:$sends');
            return http.Response('fixture-result', sends == 1 || mode == 'rejected-again' ? 401 : 200);
          });
      final result = await executeApi<String>(
          request: const ApiRequest(
              url: 'http://127.0.0.1:1/conversations',
              method: 'POST',
              headers: {'X-Fixture': 'preserved'},
              body: 'fixture-body'),
          execution: execution,
          decode: (body) {
            decodes++;
            return body;
          });
      final replayed = mode == 'recovered' || mode == 'rejected-again';
      expect(events.where((e) => e == 'refresh'), hasLength(1));
      expect(events.where((e) => e == 'headers'), hasLength(replayed ? 2 : 1));
      expect(sends, replayed ? 2 : 1);
      expect(events.take(3), ['headers', 'send:1', 'refresh']);
      if (mode == 'recovered') {
        expect((result as ApiSuccess<String>).data, 'fixture-result');
        expect(decodes, 1);
        expect(auth.expired, isEmpty);
        expect(events.last, 'record:true:refresh_succeeded');
      } else {
        expect((result as ApiFailure<String>).problem.kind,
            mode == 'transient' ? ApiProblemKind.authTransient : ApiProblemKind.authTerminal);
        expect(decodes, 0);
        expect(auth.expired, hasLength(mode == 'transient' ? 0 : 1));
        if (mode == 'rejected-again') {
          expect(auth.expired.single.reason, AuthSessionExpirationReason.backendRejectedRefreshedToken);
        }
      }
    });
  }
}
