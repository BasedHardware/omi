import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/task_suggestions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/api_fallback.dart';
import 'package:uuid/uuid.dart';

/// Presentation state only. Candidate acceptance remains the sole task creation authority.
/// Owned and reset by ActionItemsProvider, including while a request is outstanding.
class TaskSuggestionsController extends ChangeNotifier {
  TaskSuggestionsController({required TaskSuggestionsApi api, required Future<bool> Function(String) onTaskSaved})
      : _api = api,
        _onTaskSaved = onTaskSaved;

  final TaskSuggestionsApi _api;
  final Future<bool> Function(String) _onTaskSaved;
  int _epoch = 0;
  bool _disposed = false;
  Future<void>? _loading;
  List<TaskSuggestion> items = [];
  bool loaded = false;
  ApiProblem? loadProblem;
  final Set<String> _busy = {};
  final Map<String, String> _savedTasks = {};
  final Set<String> _resolvedIds = {};
  final Map<String, String> _summaryKeys = {};
  final Map<String, String> _savedSummaries = {};

  bool get loading => _loading != null;
  bool busy(String id) => _busy.contains(id);
  bool saved(String id) => _savedTasks.containsKey(id);

  static String description(TaskSuggestion item) =>
      item.taskChange?.create?.description ?? item.workstreamProposal?.anchorTask.description ?? '';

  Future<void> load() {
    final pending = _loading;
    if (pending != null) return pending;
    final epoch = _epoch;
    final request = _load();
    _loading = request;
    _notify();
    return request.whenComplete(() {
      if (_current(epoch) && identical(_loading, request)) {
        _loading = null;
        _notify();
      }
    });
  }

  Future<void> _load() async {
    final epoch = _epoch;
    // An acknowledged save must be read back, never accepted/created a second time.
    for (final id in _savedTasks.keys.toList()) {
      await retrySaved(id);
      if (!_current(epoch)) return;
    }
    final result = await _api.list();
    if (!_current(epoch)) return;
    if (result case ApiSuccess(:final data)) {
      final pendingSaved = items.where((item) => saved(item.candidateId)).toList();
      final seen = <String>{};
      items = [...pendingSaved, ...data.where((item) => !_resolvedIds.contains(item.candidateId))]
          .where((item) => seen.add(item.candidateId))
          .toList();
      loaded = true;
      loadProblem = null;
    } else if (result case ApiFailure(:final problem)) {
      loadProblem = problem;
      // Keep stale proposals only while the presentation contract permits protected data.
      final view = presentApiResult<List<TaskSuggestion>>(result,
          previous: items, isEmpty: (items) => items.isEmpty, fallback: recordFallback);
      if (view.data == null) items = [];
    }
    _notify();
  }

  Future<bool> accept(TaskSuggestion item) async {
    final id = item.candidateId;
    if (!_busy.add(id)) return false;
    final epoch = _epoch;
    _notify();
    try {
      if (saved(id)) return await _hydrate(id, epoch);
      final result = await _api.accept(item);
      if (!_current(epoch)) return false;
      if (result case ApiSuccess(:final data)) {
        _resolvedIds.add(id);
        _savedTasks[id] = data.taskId!;
        await _hydrate(id, epoch);
        // The receipt is durable even when refreshing the list fails.
        return _current(epoch);
      }
      return false;
    } finally {
      if (_current(epoch)) {
        _busy.remove(id);
        _notify();
      }
    }
  }

  Future<bool> retrySaved(String id) async {
    if (!_savedTasks.containsKey(id) || !_busy.add(id)) return false;
    final epoch = _epoch;
    _notify();
    try {
      return await _hydrate(id, epoch);
    } finally {
      if (_current(epoch)) {
        _busy.remove(id);
        _notify();
      }
    }
  }

  Future<bool> _hydrate(String id, int epoch) async {
    final taskId = _savedTasks[id];
    if (taskId == null || !_current(epoch)) return false;
    final visible = await _onTaskSaved(taskId);
    if (!_current(epoch) || !visible) return false;
    _savedTasks.remove(id);
    items = items.where((item) => item.candidateId != id).toList();
    return true;
  }

  Future<bool> dismiss(TaskSuggestion item) async {
    final id = item.candidateId;
    if (saved(id) || !_busy.add(id)) return false;
    final epoch = _epoch;
    _notify();
    try {
      final result = await _api.dismiss(item);
      if (!_current(epoch) || result is! ApiSuccess<TaskSuggestionReceipt>) return false;
      if (result.data.status != 'rejected') return false;
      _resolvedIds.add(id);
      items = items.where((item) => item.candidateId != id).toList();
      return true;
    } finally {
      if (_current(epoch)) {
        _busy.remove(id);
        _notify();
      }
    }
  }

  /// A separate reader gesture prepares and then accepts the server's stored summary row.
  /// Desktop-origin summaries only: phone extraction already writes its admitted tasks.
  Future<bool> addSummaryTask(String conversationId, int index, String expectedDescription) async {
    final reference = {
      'conversation_id': conversationId,
      'action_item_index': index,
      'expected_description': expectedDescription,
    };
    final id = '$conversationId/$index/$expectedDescription';
    if (!_busy.add(id)) return false;
    final epoch = _epoch;
    _notify();
    try {
      final savedTask = _savedSummaries[id];
      if (savedTask != null) {
        final visible = await _onTaskSaved(savedTask);
        return _current(epoch) && visible;
      }
      final generation = await _api.generation();
      if (!_current(epoch) || generation is! ApiSuccess<int>) return false;
      var prepared = await _api.prepareSummary(
        reference: reference,
        generation: generation.data,
        idempotencyKey: _summaryKeys.putIfAbsent(id, () => const Uuid().v4()),
      );
      if (!_current(epoch) || prepared is! ApiSuccess<TaskSuggestion>) return false;
      if (_terminalSummaryCandidate(prepared.data)) {
        // A fresh explicit gesture may replace a terminal proposal. Ambiguous
        // transport failures keep the old key so an accepted task is replayed.
        _summaryKeys.remove(id);
        prepared = await _api.prepareSummary(
          reference: reference,
          generation: generation.data,
          idempotencyKey: _summaryKeys.putIfAbsent(id, () => const Uuid().v4()),
        );
        if (!_current(epoch) || prepared is! ApiSuccess<TaskSuggestion>) return false;
        if (_terminalSummaryCandidate(prepared.data)) {
          _summaryKeys.remove(id);
          return false;
        }
      }
      final candidate = prepared.data;
      final accepted = await _api.accept(candidate, summary: reference);
      if (!_current(epoch)) return false;
      if (accepted is! ApiSuccess<TaskSuggestionReceipt>) {
        if (accepted case ApiFailure(problem: final problem) when problem.statusCode == 409) {
          final current = await _api.get(candidate.candidateId);
          if (_current(epoch) && current is ApiSuccess<TaskSuggestion> && _terminalSummaryCandidate(current.data)) {
            _summaryKeys.remove(id);
          }
        }
        return false;
      }
      _savedSummaries[id] = accepted.data.taskId!;
      _resolvedIds.add(candidate.candidateId);
      _savedTasks[candidate.candidateId] = accepted.data.taskId!;
      if (!items.any((item) => item.candidateId == candidate.candidateId)) items = [...items, candidate];
      await _hydrate(candidate.candidateId, epoch);
      if (!_current(epoch)) return false;
      return true;
    } finally {
      if (_current(epoch)) {
        _busy.remove(id);
        _notify();
      }
    }
  }

  bool _terminalSummaryCandidate(TaskSuggestion item) =>
      item.status == 'rejected' ||
      item.status == 'expired' ||
      (item.status == 'pending' && item.expiresAt != null && !item.expiresAt!.isAfter(DateTime.now()));

  bool summarySaved(String conversationId, int index, String description) =>
      _savedSummaries.containsKey('$conversationId/$index/$description');

  void reset() {
    _epoch++;
    _loading = null;
    items = [];
    loaded = false;
    loadProblem = null;
    _busy.clear();
    _savedTasks.clear();
    _resolvedIds.clear();
    _summaryKeys.clear();
    _savedSummaries.clear();
    _notify();
  }

  bool _current(int epoch) => !_disposed && epoch == _epoch;
  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _epoch++;
    super.dispose();
  }
}
