import 'dart:async';

import 'package:flutter/foundation.dart';

class Debouncer {
  Debouncer({this.delay});

  Duration? delay;
  VoidCallback? _action;

  Timer? _timer;

  void run(VoidCallback action) {
    _action = action;
    _timer?.cancel();
    if (delay != null) {
      _timer = Timer(delay!, () {
        if (_action != null) {
          _action!();
        }
      });
    }
  }

  void cancel() {
    _timer?.cancel();
    _action = null;
  }
}
