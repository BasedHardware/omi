import 'package:omi/services/sockets/pure_socket.dart';

/// Pass-through transport for the `localOnly` policy.
///
/// This type intentionally owns only the Custom STT primary socket. The Omi
/// secondary is not allocated, so it cannot be connected or become a hidden
/// dependency of the local transcript path.
class LocalOnlyTranscriptionSocket implements IPureSocket {
  final IPureSocket primarySocket;

  IPureSocketListener? _listener;
  late final _LocalOnlyPrimaryListener _primaryListener;

  LocalOnlyTranscriptionSocket({required this.primarySocket}) {
    _primaryListener = _LocalOnlyPrimaryListener(this);
    primarySocket.setListener(_primaryListener);
  }

  @override
  PureSocketStatus get status => primarySocket.status;

  @override
  void setListener(IPureSocketListener listener) {
    _listener = listener;
  }

  @override
  Future<bool> connect() => primarySocket.connect();

  @override
  Future disconnect() => primarySocket.disconnect();

  @override
  Future stop() => primarySocket.stop();

  @override
  void send(dynamic message) => primarySocket.send(message);

  @override
  void onConnected() => _listener?.onConnected();

  @override
  void onMessage(dynamic message) => _listener?.onMessage(message);

  @override
  void onClosed([int? closeCode]) => _listener?.onClosed(closeCode);

  @override
  void onError(Object err, StackTrace trace) => _listener?.onError(err, trace);
}

class _LocalOnlyPrimaryListener implements IPureSocketListener {
  final LocalOnlyTranscriptionSocket _owner;

  _LocalOnlyPrimaryListener(this._owner);

  @override
  void onConnected() => _owner.onConnected();

  @override
  void onMessage(dynamic message) => _owner.onMessage(message);

  @override
  void onClosed([int? closeCode]) => _owner.onClosed(closeCode);

  @override
  void onError(Object err, StackTrace trace) => _owner.onError(err, trace);
}
