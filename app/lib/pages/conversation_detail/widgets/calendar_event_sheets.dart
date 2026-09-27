import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

const _googleCalendarLogo = 'assets/integration_app_logos/google-calendar.png';

/// How a calendar attendee is named on the detail page: the attendee's display name when the
/// calendar gave one, otherwise the whole local part of the address ("john.doe", not "John.doe"
/// or just "John").
String formatAttendeeName(String attendee) {
  final value = attendee.trim();
  if (!value.contains('@')) return value;
  final localPart = value.split('@').first;
  return localPart.isEmpty ? value : localPart;
}

/// "Ann Lee", "Ann Lee, john.doe", or "Ann Lee, john.doe +3".
String formatAttendeesLabel(List<String> attendees) {
  if (attendees.isEmpty) return '';
  final shown = attendees.take(2).map(formatAttendeeName).join(', ');
  return attendees.length > 2 ? '$shown +${attendees.length - 2}' : shown;
}

/// Opens the picker that links the open conversation to a calendar event.
Future<void> showLinkEventSheet(BuildContext context) {
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.linkEvent,
    padding: EdgeInsets.zero,
    builder: (_) => const CalendarEventPickerSheet(),
  );
}

/// Shows the event a conversation is linked to, with its time, attendees and actions.
Future<void> showCalendarEventDetailsSheet(
  BuildContext context,
  CalendarEventLink calendarEvent, {
  Future<void> Function()? onUnlink,
}) {
  return showOmiSheet<void>(
    context: context,
    title: calendarEvent.title,
    builder: (_) => CalendarEventDetailsSheet(calendarEvent: calendarEvent, onUnlink: onUnlink),
  );
}

/// Body of the link-event sheet (present it with [showLinkEventSheet]).
class CalendarEventPickerSheet extends StatefulWidget {
  const CalendarEventPickerSheet({super.key});

  @override
  State<CalendarEventPickerSheet> createState() => _CalendarEventPickerSheetState();
}

class _CalendarEventPickerSheetState extends State<CalendarEventPickerSheet> {
  List<CalendarEventLink> _events = [];
  String? _suggestedEventId;
  bool _isLoading = true;
  bool _isLinking = false;
  String? _linkingEventId;

  @override
  void initState() {
    super.initState();
    _loadEvents();
  }

  Future<void> _loadEvents() async {
    final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
    final events = await provider.listCalendarEventsForPicker();
    if (!mounted) return;

    final conversation = provider.conversation;
    final conversationStart = conversation.startedAt ?? conversation.createdAt;
    final conversationEnd = conversation.finishedAt ?? conversationStart.add(const Duration(hours: 1));

    String? bestMatchId;
    double bestOverlapSeconds = 0;
    for (final event in events) {
      final overlapStart = event.startTime.isAfter(conversationStart) ? event.startTime : conversationStart;
      final overlapEnd = event.endTime.isBefore(conversationEnd) ? event.endTime : conversationEnd;
      final overlapDuration = overlapEnd.difference(overlapStart).inSeconds.toDouble();
      if (overlapDuration <= 0) continue;
      final eventDuration = event.endTime.difference(event.startTime).inSeconds.toDouble();
      final overlapPercentage = eventDuration > 0 ? overlapDuration / eventDuration : 0;
      if ((overlapDuration >= 300 || overlapPercentage >= 0.5) && overlapDuration > bestOverlapSeconds) {
        bestOverlapSeconds = overlapDuration;
        bestMatchId = event.eventId;
      }
    }

    final sortedEvents = List<CalendarEventLink>.from(events);
    if (bestMatchId != null) {
      sortedEvents.sort((a, b) {
        if (a.eventId == bestMatchId) return -1;
        if (b.eventId == bestMatchId) return 1;
        return a.startTime.compareTo(b.startTime);
      });
    }

    setState(() {
      _events = sortedEvents;
      _suggestedEventId = bestMatchId;
      _isLoading = false;
    });
  }

  Future<void> _linkEvent(CalendarEventLink event) async {
    setState(() {
      _isLinking = true;
      _linkingEventId = event.eventId;
    });
    OmiHaptics.medium();

    final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
    final linked = await provider.linkCalendarEvent(event.eventId);
    if (!mounted) return;

    if (linked != null) {
      OmiFeedback.confirm(context, context.l10n.linkedToEvent(event.title));
      Navigator.pop(context);
    } else {
      setState(() {
        _isLinking = false;
        _linkingEventId = null;
      });
      OmiFeedback.error(context, context.l10n.failedToLinkCalendarEvent);
    }
  }

  Widget _buildShimmerList() {
    Widget bar({required double height, double? width}) => Container(
          height: height,
          width: width ?? double.infinity,
          decoration: const BoxDecoration(color: OmiColors.textPrimary, borderRadius: OmiRadius.smAll),
        );
    return Shimmer.fromColors(
      baseColor: OmiColors.surface2,
      highlightColor: OmiColors.surface3,
      child: ListView.builder(
        shrinkWrap: true,
        padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
        itemCount: 4,
        itemBuilder: (context, index) => Padding(
          padding: const EdgeInsets.all(OmiSpacing.md),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              bar(height: 36, width: 36),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [bar(height: 14), const SizedBox(height: 10), bar(height: 12, width: 140)],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEventTile(CalendarEventLink event, bool isSuggested, bool isLinkingThis) {
    final dates = OmiDateFormat.of(context);
    final when = '${dates.dayHeader(event.startTime)}, ${dates.timeRange(event.startTime, event.endTime)}';
    return Semantics(
      button: true,
      enabled: !_isLinking,
      child: InkWell(
        onTap: _isLinking ? null : () => _linkEvent(event),
        child: Padding(
          padding: const EdgeInsets.all(OmiSpacing.md),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: OmiRadius.smAll,
                child: Image.asset(_googleCalendarLogo, width: 36, height: 36, fit: BoxFit.cover),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      event.title,
                      style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: OmiSpacing.xxs),
                    Text(when, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                    if (isSuggested) ...[
                      const SizedBox(height: OmiSpacing.xxs),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: 2),
                        decoration: const BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.pillAll),
                        child: Text(
                          context.l10n.suggestedEvent,
                          style: OmiType.caption.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: OmiSpacing.sm),
              _isLinking && isLinkingThis
                  ? const OmiSpinner(size: OmiSpinnerSize.small)
                  : Icon(
                      Icons.add_circle_outline,
                      color: _isLinking ? OmiColors.textDisabled : OmiColors.textTertiary,
                      size: 22,
                    ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final Widget body;
    if (_isLoading) {
      body = _buildShimmerList();
    } else if (_events.isEmpty) {
      body = Padding(
        padding: const EdgeInsets.all(OmiSpacing.xxl),
        child: Text(
          context.l10n.noCalendarEventsNearby,
          style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
          textAlign: TextAlign.center,
        ),
      );
    } else {
      body = ListView.separated(
        shrinkWrap: true,
        padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
        itemCount: _events.length,
        separatorBuilder: (_, __) =>
            const Divider(color: OmiColors.border, height: 1, indent: OmiSpacing.md, endIndent: OmiSpacing.md),
        itemBuilder: (context, index) {
          final event = _events[index];
          return _buildEventTile(event, event.eventId == _suggestedEventId, _linkingEventId == event.eventId);
        },
      );
    }
    return ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.6),
      child: body,
    );
  }
}

/// Body of the linked-event sheet (present it with [showCalendarEventDetailsSheet]).
class CalendarEventDetailsSheet extends StatefulWidget {
  final CalendarEventLink calendarEvent;
  final Future<void> Function()? onUnlink;

  const CalendarEventDetailsSheet({super.key, required this.calendarEvent, this.onUnlink});

  @override
  State<CalendarEventDetailsSheet> createState() => _CalendarEventDetailsSheetState();
}

class _CalendarEventDetailsSheetState extends State<CalendarEventDetailsSheet> {
  bool _unlinking = false;

  Future<void> _shareWithAttendees() async {
    final emails = widget.calendarEvent.attendeeEmails;
    if (emails.isEmpty) return;
    final subject = Uri.encodeComponent(context.l10n.meetingNotesSubject(widget.calendarEvent.title));
    await launchUrl(Uri.parse('mailto:${emails.join(',')}?subject=$subject'));
  }

  @override
  Widget build(BuildContext context) {
    final event = widget.calendarEvent;
    final dates = OmiDateFormat.of(context);
    final secondary = OmiType.subhead.copyWith(color: OmiColors.textSecondary);
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.access_time, size: 16, color: OmiColors.textTertiary),
              const SizedBox(width: OmiSpacing.xs),
              Expanded(child: Text(dates.timeRange(event.startTime, event.endTime), style: secondary)),
            ],
          ),
          if (event.attendees.isNotEmpty) ...[
            const SizedBox(height: OmiSpacing.sm),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.people_outline, size: 16, color: OmiColors.textTertiary),
                const SizedBox(width: OmiSpacing.xs),
                Expanded(child: Text(event.attendees.map(formatAttendeeName).join(', '), style: secondary)),
              ],
            ),
          ],
          const SizedBox(height: OmiSpacing.md),
          const Divider(color: OmiColors.border),
          if (event.htmlLink != null)
            _ActionRow(
              icon: Icons.open_in_new,
              label: context.l10n.openInGoogleCalendar,
              onTap: () => launchUrl(Uri.parse(event.htmlLink!), mode: LaunchMode.externalApplication),
            ),
          if (event.attendeeEmails.isNotEmpty)
            _ActionRow(icon: Icons.share_outlined, label: context.l10n.shareWithAttendees, onTap: _shareWithAttendees),
          if (widget.onUnlink != null)
            _ActionRow(
              icon: Icons.link_off,
              label: context.l10n.unlinkCalendarEvent,
              color: OmiColors.danger,
              loading: _unlinking,
              onTap: () async {
                setState(() => _unlinking = true);
                await widget.onUnlink!();
                if (!context.mounted) return;
                Navigator.pop(context);
              },
            ),
        ],
      ),
    );
  }
}

class _ActionRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback? onTap;
  final Color color;
  final bool loading;

  const _ActionRow({
    required this.icon,
    required this.label,
    this.onTap,
    this.color = OmiColors.textPrimary,
    this.loading = false,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      child: InkWell(
        onTap: loading ? null : onTap,
        borderRadius: OmiRadius.smAll,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm, horizontal: OmiSpacing.xxs),
            child: Row(
              children: [
                loading ? OmiSpinner(size: OmiSpinnerSize.small, color: color) : Icon(icon, size: 20, color: color),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(child: Text(label, style: OmiType.subhead.copyWith(color: color))),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
