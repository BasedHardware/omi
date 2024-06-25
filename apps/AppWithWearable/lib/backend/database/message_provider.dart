import 'package:friend_private/backend/database/box.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/objectbox.g.dart';

class MessageProvider {
  static final MessageProvider _instance = MessageProvider._internal();
  static final Box<Message> _box = ObjectBoxUtil().box!.store.box<Message>();

  factory MessageProvider() {
    if (_box.isEmpty()) {
      _box.put(Message(DateTime.now(), 'What would you like to search for?', 'ai'));
    }
    return _instance;
  }

  MessageProvider._internal();

  List<Message> getMessages() => _box.getAll();

  Stream<Query<Message>> getMessagesStreamed() => _box.query().watch(triggerImmediately: true);

  Future<void> saveMessage(Message message) async => _box.put(message);

  Future<void> updateMessage(Message message) async => _box.put(message);

  Future<List<Message>> retrieveMostRecentMessages({int limit = 5}) async {
    var query = _box.query().order(Message_.createdAt, flags: Order.descending).build();
    query.limit = limit;
    return query.find();
  }

  int getMessagesCount() => _box.count();
}
