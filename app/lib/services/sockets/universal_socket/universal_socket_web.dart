import 'package:web/web.dart' as web;
import 'package:web_socket_channel/html.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

Future<WebSocketChannel> createUniversalSocket(String url, {Map<String, dynamic>? headers, required Duration pingInterval, required Duration connectTimeout}) async {
  final socket = web.WebSocket(url.toString());
  return HtmlWebSocketChannel(socket);
}
