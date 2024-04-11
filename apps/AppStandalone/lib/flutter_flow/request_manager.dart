// ignore_for_file: close_sinks

import 'dart:async';

import 'package:rxdart/rxdart.dart';
import 'package:rxdart/subjects.dart';

class FutureRequestManager<T> {
  FutureRequestManager([this.cacheLimit = 10]);

  final int cacheLimit;
  final Map<String, Future<T>> _requests = {};
  Future<T> performRequest({
    String? uniqueQueryKey,
    bool? overrideCache,
    required Future<T> Function() requestFn,
  }) {
    uniqueQueryKey = _requestKey(uniqueQueryKey);
    overrideCache ??= false;

    // If we don't want to use the cache, clear it for this request.
    if (overrideCache) {
      clearRequest(uniqueQueryKey);
    }
    // Remove the first cached result if we have reached the specified limit,
    // since we will be adding another.
    if (!_requests.containsKey(uniqueQueryKey) &&
        _requests.length >= cacheLimit) {
      _requests.remove(_requests.keys.first);
    }
    // Return the cached query result or set it to the new value.
    return _requests[uniqueQueryKey] ??= requestFn();
  }

  void clearRequest(String? key) => _requests.remove(_requestKey(key));

  void clear() => _requests.keys.toList().forEach(clearRequest);
}

class StreamRequestManager<T> {
  StreamRequestManager([this.cacheLimit = 10]);

  final int cacheLimit;
  final Map<String, BehaviorSubject<T>> _streamSubjects = {};
  final Map<String, StreamSubscription<T>> _requestSubscriptions = {};
  Stream<T> performRequest({
    String? uniqueQueryKey,
    bool? overrideCache,
    required Stream<T> Function() requestFn,
  }) {
    uniqueQueryKey = _requestKey(uniqueQueryKey);
    overrideCache ??= false;

    // If we don't want to use the cache, clear it for this request.
    if (overrideCache) {
      clearRequest(uniqueQueryKey);
    }

    // If this request was made previously, return its value stream.
    if (_streamSubjects.containsKey(uniqueQueryKey)) {
      return _streamSubjects[uniqueQueryKey]!.stream;
    }

    // Remove the first cached result if we have reached the specified limit,
    // since we will be adding another.
    if (_streamSubjects.isNotEmpty && _streamSubjects.length >= cacheLimit) {
      clearRequest(_streamSubjects.keys.first);
    }

    // Create a subscription that stores the latest result in the behavior subject.
    final streamSubject = BehaviorSubject<T>();
    _requestSubscriptions[uniqueQueryKey] = requestFn()
        .asBroadcastStream()
        .listen((result) => streamSubject.add(result));
    _streamSubjects[uniqueQueryKey] = streamSubject;

    return streamSubject.stream;
  }

  void clearRequest(String? key) {
    key = _requestKey(key);
    _streamSubjects.remove(key)?.close();
    _requestSubscriptions.remove(key)?.cancel();
  }

  void clear() => {
        ..._streamSubjects.keys,
        ..._requestSubscriptions.keys,
      }.forEach(clearRequest);
}

String _requestKey(String? key) =>
    key == null || key.isEmpty ? '__DEFAULT_KEY__' : key;
