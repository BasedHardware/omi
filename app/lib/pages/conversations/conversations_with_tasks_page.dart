// Server-backed task conversation browse/search. Filters and continuations stay
// account-owned, and this pushed route preserves the Home/search place on Back.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversation_tasks.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_task_presence_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';

typedef TaskConversationFetcher = Future<ApiResult<TaskConversationPage>> Function({
  required String query,
  bool includeDiscarded,
  String? folderId,
  bool? starred,
  DateTime? startDate,
  DateTime? endDate,
  String? cursor,
  bool Function()? canSend,
});

/// Search/browse destination, kept above Home so leaving it restores the Home
/// scroll position. Every page and filter is resolved by the server.
class ConversationsWithTasksPage extends StatefulWidget {
  const ConversationsWithTasksPage({super.key, this.fetch, this.auth});

  final TaskConversationFetcher? fetch;
  final AuthService? auth;

  @override
  State<ConversationsWithTasksPage> createState() => _ConversationsWithTasksPageState();
}

class _ConversationsWithTasksPageState extends State<ConversationsWithTasksPage> {
  final _query = TextEditingController();
  late final AuthService _auth = widget.auth ?? AuthService.instance;
  StreamSubscription<int>? _session;
  ConversationTaskPresenceProvider? _presence;
  int _taskRevision = 0;
  Timer? _debounce;
  int _generation = 0;
  List<ServerConversation> _rows = [];
  String? _cursor;
  bool _loading = false;
  bool _failed = false;
  bool _retryReset = true;
  String? _folder;
  bool _starred = false;
  DateTime? _start;
  DateTime? _end;

  @override
  void initState() {
    super.initState();
    _session = _auth.sessionGenerationEvents.listen((_) {
      if (!mounted) return;
      _generation++;
      setState(() {
        _rows = [];
        _cursor = null;
        _failed = true;
        _loading = false;
      });
    });
    unawaited(_load(reset: true));
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final presence = context.read<ConversationTaskPresenceProvider?>();
    if (!identical(presence, _presence)) {
      _presence?.removeListener(_tasksChanged);
      _presence = presence;
      _taskRevision = presence?.taskRevision ?? 0;
      presence?.addListener(_tasksChanged);
    }
  }

  void _tasksChanged() {
    if (_presence?.taskRevision == _taskRevision) return;
    _taskRevision = _presence?.taskRevision ?? 0;
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 250), () => _load(reset: true));
  }

  void _filtersChanged() {
    _generation++;
    _debounce?.cancel();
    setState(() {
      _rows = [];
      _cursor = null;
      _failed = false;
      _loading = true;
    });
    _debounce = Timer(const Duration(milliseconds: 250), () => _load(reset: true));
  }

  Future<void> _load({bool reset = false}) async {
    if (!mounted || (_loading && !reset)) return;
    final owner = _auth.captureSessionSnapshot();
    final generation = ++_generation;
    final cursor = reset ? null : _cursor;
    _retryReset = reset;
    setState(() {
      _loading = true;
      _failed = false;
    });
    bool current() => mounted && generation == _generation && owner != null && _auth.isSessionSnapshotCurrent(owner);
    try {
      if (owner == null) throw StateError('No authenticated task-filter owner');
      final fetch = widget.fetch ?? getConversationsWithTasks;
      final result = await fetch(
        query: _query.text.trim(),
        includeDiscarded: SharedPreferencesUtil().showDiscardedMemories,
        folderId: _folder,
        starred: _starred ? true : null,
        startDate: _start,
        endDate: _end,
        cursor: cursor,
        canSend: current,
      ).timeout(const Duration(seconds: 25));
      if (!current()) {
        if (mounted && generation == _generation) {
          setState(() {
            _rows = [];
            _cursor = null;
            _failed = true;
          });
        }
        return;
      }
      switch (result) {
        case ApiSuccess(:final data):
          if (cursor != null && data.nextCursor == cursor) {
            setState(() {
              _cursor = null;
              _failed = true;
              _retryReset = true;
            });
            return;
          }
          setState(() {
            final byId = {
              if (!reset)
                for (final row in _rows) row.id: row
            };
            for (final row in data.items) {
              byId[row.id] = row;
            }
            _rows = byId.values.toList();
            _cursor = data.nextCursor;
          });
        case ApiFailure(:final problem):
          final hideProtectedRows = switch (problem.kind) {
            ApiProblemKind.authTerminal ||
            ApiProblemKind.forbidden ||
            ApiProblemKind.paymentRequired ||
            ApiProblemKind.notFound ||
            ApiProblemKind.unprocessable ||
            ApiProblemKind.rejected =>
              true,
            _ => false,
          };
          setState(() {
            _failed = true;
            if (hideProtectedRows) {
              _rows = [];
              _cursor = null;
              _retryReset = true;
            }
          });
      }
    } catch (_) {
      if (mounted && generation == _generation) {
        setState(() {
          _failed = true;
          if (owner == null || !_auth.isSessionSnapshotCurrent(owner)) {
            _rows = [];
            _cursor = null;
            _retryReset = true;
          }
        });
      }
    } finally {
      if (mounted && generation == _generation) setState(() => _loading = false);
    }
  }

  Future<void> _pickDate() => showConversationDateRangePicker(
        context,
        initialStartDate: _start,
        initialEndDate: _end,
        onSelected: (start, end) {
          _start = DateTime(start.year, start.month, start.day);
          _end = DateTime(end.year, end.month, end.day + 1).subtract(const Duration(microseconds: 1));
          _filtersChanged();
        },
        onClear: () {
          _start = null;
          _end = null;
          _filtersChanged();
        },
      );

  @override
  void dispose() {
    _generation++;
    _debounce?.cancel();
    _session?.cancel();
    _presence?.removeListener(_tasksChanged);
    _query.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final folders = context.watch<FolderProvider?>()?.folders ?? const [];
    return Scaffold(
      key: const ValueKey('conversations_with_tasks_page'),
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.hasTasksFilter), actions: [
        IconButton(
            key: const ValueKey('tasks_filter_refresh'),
            tooltip: l10n.refresh,
            onPressed: () => _load(reset: true),
            icon: const Icon(Icons.refresh)),
      ]),
      body: Column(children: [
        Padding(
            padding: const EdgeInsets.all(OmiSpacing.md),
            child: Column(children: [
              OmiSearchField(
                  key: const ValueKey('tasks_filter_query'),
                  placeholder: l10n.searchConversations,
                  controller: _query,
                  onChanged: (_) => _filtersChanged()),
              const SizedBox(height: OmiSpacing.xs),
              Wrap(
                  spacing: OmiSpacing.xs,
                  runSpacing: OmiSpacing.xs,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    FilterChip(
                        key: const ValueKey('tasks_filter_starred'),
                        label: Text(l10n.starred),
                        selected: _starred,
                        onSelected: (value) {
                          _starred = value;
                          _filtersChanged();
                        }),
                    ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 200),
                        child: DropdownButton<String>(
                          key: const ValueKey('tasks_filter_folder'),
                          value: _folder ?? '',
                          isExpanded: true,
                          hint: Text(l10n.folderName),
                          items: [
                            DropdownMenuItem(value: '', child: Text(l10n.all)),
                            if (_folder != null && !folders.any((f) => f.id == _folder))
                              DropdownMenuItem(value: _folder, child: Text(l10n.folderName)),
                            for (final f in folders)
                              DropdownMenuItem(value: f.id, child: Text(f.name, overflow: TextOverflow.ellipsis))
                          ],
                          onChanged: (value) {
                            _folder = value == '' ? null : value;
                            _filtersChanged();
                          },
                        )),
                    IconButton(
                        key: const ValueKey('tasks_filter_date'),
                        tooltip: l10n.filterByDate,
                        onPressed: _pickDate,
                        icon: const Icon(Icons.calendar_month_outlined)),
                    if (_start != null)
                      OmiDateFilterChip(
                          start: _start!,
                          end: _end,
                          onClear: () {
                            _start = null;
                            _end = null;
                            _filtersChanged();
                          }),
                  ]),
            ])),
        Expanded(
            child: ListView.builder(
          key: const PageStorageKey('task_conversation_results'),
          itemCount: _rows.length + 1,
          itemBuilder: (context, index) {
            if (index < _rows.length) {
              final row = _rows[index];
              return ConversationListItem(
                key: ValueKey('task_conversation_${row.id}'),
                conversation: row,
                date: row.createdAt,
                conversationIdx: index,
                allowSelection: false,
                hasLinkedTasks: true,
              );
            }
            return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              if (_loading) const Padding(padding: EdgeInsets.all(OmiSpacing.lg), child: Center(child: OmiSpinner())),
              if (_failed)
                Padding(
                    padding: const EdgeInsets.all(OmiSpacing.md),
                    child: Column(children: [
                      Text(l10n.tryAgain),
                      TextButton(
                          key: const ValueKey('tasks_filter_retry'),
                          onPressed: () => _load(reset: _retryReset),
                          child: Text(l10n.retry)),
                    ])),
              if (!_loading && !_failed && _rows.isEmpty && _cursor == null)
                OmiEmptyState(icon: Icons.checklist_rounded, title: l10n.noResultsFound),
              if (!_loading && !_failed && _cursor != null)
                TextButton(
                    key: const ValueKey('tasks_filter_more'), onPressed: () => _load(), child: Text(l10n.showMore)),
            ]);
          },
        )),
      ]),
    );
  }
}
