import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/sockets/pure_socket.dart';

void main() {
  test('socket logs omit authentication and conversation query values', () {
    expect(
      redactSocketUrlForLogs(
        'wss://api.omi.me/v4/listen?uid=user-secret&client_conversation_id=conversation-secret',
      ),
      'wss://api.omi.me/v4/listen',
    );
    expect(redactSocketUrlForLogs('not a socket URL'), '<invalid-socket-url>');
  });

  test('unavailable auth blocks a socket before opening the network', () async {
    final socket = PureSocket(
      'wss://example.invalid',
      headersProvider: () async {
        throw AuthTokenUnavailableException(
          const AuthTokenTransientFailure(failureClass: 'offline'),
        );
      },
    );

    expect(await socket.connect(), isFalse);
    expect(socket.status, PureSocketStatus.notConnected);
  });
}
