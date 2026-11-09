// Edit the connected Google account's read selection without changing event writes.
// Unsaved choices remain local; unavailable saved calendars can be removed safely.
import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/google_calendars.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/services/integrations/google_calendar_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class GoogleCalendarSelectionPage extends StatefulWidget {
  const GoogleCalendarSelectionPage({super.key, this.request = googleCalendarSelection});

  final Future<GoogleCalendarSelection> Function(String owner, {GoogleCalendarSelection? selection}) request;

  @override
  State<GoogleCalendarSelectionPage> createState() => _GoogleCalendarSelectionPageState();
}

class _GoogleCalendarSelectionPageState extends State<GoogleCalendarSelectionPage> {
  GoogleCalendarSelection? _data;
  Set<String> _selected = {};
  bool _busy = false;
  bool _failed = false;
  String? _loadedOwner;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final owner = GoogleCalendarService.meetingCacheOwner;
    setState(() {
      _busy = true;
      _failed = false;
      _data = null;
    });
    try {
      final data = await widget.request(owner);
      if (!mounted || owner != GoogleCalendarService.meetingCacheOwner) return;
      setState(() {
        _loadedOwner = owner;
        _data = data;
        _selected = {...data.selectedIds};
      });
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final data = _data;
    if (data == null || _selected.isEmpty || _busy) return;
    final owner = _loadedOwner;
    if (owner == null || owner != GoogleCalendarService.meetingCacheOwner) {
      return;
    }
    setState(() => _busy = true);
    try {
      await widget.request(
        owner,
        selection: GoogleCalendarSelection(
          data.accountId,
          data.calendars,
          _selected,
        ),
      );
      if (mounted) Navigator.of(context).pop();
    } catch (error) {
      if (mounted) {
        setState(() {
          _failed = true;
          if (error is GoogleCalendarSelectionFailure &&
              {ApiProblemKind.authTerminal, ApiProblemKind.forbidden, ApiProblemKind.notFound}
                  .contains(error.problem.kind)) {
            _data = null;
          }
        });
        OmiFeedback.error(context, context.l10n.connectionErrorDesc);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _loadedOwner == GoogleCalendarService.meetingCacheOwner ? _data : null;
    final primary = data?.calendars.where((row) => row.primary).firstOrNull;
    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.calendarSettings),
        actions: [
          OmiButton.tertiary(
            label: context.l10n.save,
            size: OmiButtonSize.compact,
            onPressed: _busy || data == null || _selected.isEmpty ? null : _save,
          ),
        ],
      ),
      body: _busy && data == null
          ? const Center(child: OmiSpinner())
          : ListView(
              padding: const EdgeInsets.all(OmiSpacing.lg),
              children: [
                if (_failed) ...[
                  Text(context.l10n.connectionErrorDesc, style: OmiType.body),
                  OmiButton.secondary(
                    onPressed: _busy ? null : _load,
                    label: context.l10n.refresh,
                  ),
                ],
                if (data != null) ...[
                  Text(
                    context.l10n.calendarReadSelectionHelp(
                      primary?.name ?? data.accountId,
                    ),
                    style: OmiType.subhead,
                  ),
                  const SizedBox(height: OmiSpacing.md),
                  for (final row in data.calendars)
                    IgnorePointer(
                      ignoring: _busy || (!row.available && !_selected.contains(row.id)),
                      child: OmiCheckboxRow(
                        key: ValueKey('calendar-${row.id}'),
                        label:
                            '${row.name.isEmpty ? row.id : row.name}${row.available ? '' : ' — ${context.l10n.chatBlockUnavailable}'}',
                        value: _selected.contains(row.id),
                        onChanged: (value) {
                          setState(() {
                            value ? _selected.add(row.id) : _selected.remove(row.id);
                          });
                        },
                      ),
                    ),
                ],
              ],
            ),
    );
  }
}
