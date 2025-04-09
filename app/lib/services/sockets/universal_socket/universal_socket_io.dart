import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

Future<WebSocketChannel> createUniversalSocket(String url, {Map<String, dynamic>? headers}) async {
  return IOWebSocketChannel.connect(
    url,
    headers: headers,
    pingInterval: const Duration(seconds: 20),
    connectTimeout: const Duration(seconds: 30),
  );
}
