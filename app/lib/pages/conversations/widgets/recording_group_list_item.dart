import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/local_recording.dart';
import 'package:omi/models/local_recording_group.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

import 'recording_list_item.dart';

/// One Home row per Watch session. The original parts and their existing
/// playback, processing, export and confirmed-delete controls stay one tap away.
class RecordingGroupListItem extends StatelessWidget {
  const RecordingGroupListItem({super.key, required this.recording});

  final LocalRecordingGroup recording;

  @override
  Widget build(BuildContext context) {
    if (!recording.isWatchRecovery) return RecordingListItem(recording: recording.recordings.single);
    final l = context.l10n;
    final failed = recording.recordings.any((r) => r.state == LocalRecordingState.failed);
    final uploading = recording.recordings.any((r) => r.state == LocalRecordingState.uploading);
    final processing = recording.recordings.any((r) => r.state == LocalRecordingState.processing);
    final status = failed
        ? l.failedStatus
        : uploading
            ? l.syncStatusBackingUp
            : processing
                ? l.syncStatusUploaded
                : l.privateAndSecureOnDevice;
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(OmiSpacing.lg, OmiSpacing.md, OmiSpacing.lg, 0),
      child: Material(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.xlAll,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          key: ValueKey('watch_session_${recording.id}'),
          onTap: () => routeToPage(context, WatchRecordingSessionPage(sessionId: recording.id)),
          child: Padding(
            padding: const EdgeInsets.all(OmiSpacing.lg),
            child: Row(children: [
              Icon(Icons.watch_outlined, color: OmiColors.textSecondary),
              const SizedBox(width: OmiSpacing.md),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(
                    '${OmiDateFormat.of(context).time(recording.startedAt)} · ${OmiDuration.compact(recording.seconds, l)}',
                    style: OmiType.callout.copyWith(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: OmiSpacing.xs),
                  Text(status,
                      style: OmiType.footnote.copyWith(color: failed ? OmiColors.danger : OmiColors.textSecondary)),
                ]),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Icon(Icons.chevron_right, color: OmiColors.textTertiary),
            ]),
          ),
        ),
      ),
    );
  }
}

class WatchRecordingSessionPage extends StatelessWidget {
  const WatchRecordingSessionPage({super.key, required this.sessionId});

  final String sessionId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.recordings)),
      body: Consumer<LocalRecordingsProvider>(builder: (context, provider, _) {
        final recording = provider.homeRecordings.where((group) => group.id == sessionId).firstOrNull;
        if (recording == null) {
          return OmiEmptyState(icon: Icons.watch_outlined, title: context.l10n.noRecordings);
        }
        return ListView.builder(
          key: const ValueKey('watch_session_recordings'),
          padding: const EdgeInsets.only(bottom: OmiSpacing.xl),
          itemCount: recording.recordings.length,
          itemBuilder: (context, index) => RecordingListItem(
            key: ValueKey(recording.recordings[index].id),
            recording: recording.recordings[index],
          ),
        );
      }),
    );
  }
}
