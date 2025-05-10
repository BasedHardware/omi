import 'package:omi/backend/schema/message_event.dart';

abstract interface class IWalSocketServiceListener {
  void onMessageEventReceived(ServerMessageEvent event);

  void onError(Object err);

  void onConnected();

  void onClosed();
}
