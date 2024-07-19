import 'package:friend_private/backend/database/box.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/objectbox.g.dart';

class MessageProvider {
  static final MessageProvider _instance = MessageProvider._internal();
  static final Box<Message> _box = ObjectBoxUtil().box!.store.box<Message>();

  factory MessageProvider() {
    return _instance;
  }

  MessageProvider._internal();

  List<Message> getMessages() => _box.getAll();

  Stream<Query<Message>> getMessagesStreamed() => _box.query().watch(triggerImmediately: true);

  Future<void> saveMessage(Message message) async => _box.put(message);

  Future<void> updateMessage(Message message) async => _box.put(message);

  Future<List<Message>> retrieveMostRecentMessages({int limit = 5, String? pluginId}) async {
    Query<Message> query = _box
        .query(
          Message_.fromIntegration.equals(false), // determine if keep
        )
        .order(Message_.createdAt, flags: Order.descending)
        .build();
    query.limit = limit;
    var messages = query.find();

    // get the index from 0 to n, where message.sender == 'ai' and pluginId  matches, then sublist
    var idx = 0;
    for (var i = 0; i < messages.length; i++) {
      if (messages[i].sender == 'ai') {
        if (pluginId == messages[i].pluginId) {
          idx = i;
        } else {
          break;
        }
      }
    }
    if (messages.isNotEmpty && messages[0].sender == 'ai' && messages[0].text == '') {
      return messages.sublist(1, idx + 1);
    }
    return messages.sublist(0, idx + 1);
  }

  int getMessagesCount() => _box.count();
}
