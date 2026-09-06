import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/maps_util.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/widgets/omi_map_preview.dart';

const _mapClusterDistanceMeters = 100.0;
const _mapDistance = Distance(roundResult: false);

class ConversationMapGroup {
  const ConversationMapGroup({required this.latitude, required this.longitude, required this.conversations});

  final double latitude;
  final double longitude;
  final List<ServerConversation> conversations;

  /// Stable cluster membership identity for widget automation. Sorting makes
  /// this independent of fetch/group insertion order.
  String get membershipKey {
    final ids = conversations.map((conversation) => conversation.id).toList()..sort();
    return Uri.encodeComponent(ids.join(','));
  }
}

/// Builds stable ~100m clusters and drops malformed/missing coordinates without
/// affecting the surrounding conversation surface.
List<ConversationMapGroup> buildConversationMapGroups(Iterable<ServerConversation> conversations) {
  final located = <(ServerConversation, LatLng)>[];
  for (final conversation in conversations) {
    final latitude = conversation.geolocation?.latitude;
    final longitude = conversation.geolocation?.longitude;
    if (latitude == null ||
        longitude == null ||
        !latitude.isFinite ||
        !longitude.isFinite ||
        latitude < -90 ||
        latitude > 90 ||
        longitude < -180 ||
        longitude > 180) {
      continue;
    }
    located.add((conversation, LatLng(latitude, longitude)));
  }

  // Sort before grouping so marker membership and row order do not depend on
  // the order in which paginated/provider data happened to arrive. Group by
  // actual distance rather than rounded coordinate strings: rounding creates
  // artificial boundaries where points only metres apart become separate pins.
  located.sort((a, b) => a.$1.id.compareTo(b.$1.id));
  final grouped = <({LatLng anchor, List<LatLng> points, List<ServerConversation> conversations})>[];
  for (final (conversation, point) in located) {
    final group =
        grouped.cast<({LatLng anchor, List<LatLng> points, List<ServerConversation> conversations})?>().firstWhere(
              (candidate) => candidate!.points.every(
                (member) => _mapDistance.as(LengthUnit.Meter, member, point) <= _mapClusterDistanceMeters,
              ),
              orElse: () => null,
            );
    if (group == null) {
      grouped.add((anchor: point, points: [point], conversations: [conversation]));
    } else {
      group.points.add(point);
      group.conversations.add(conversation);
    }
  }

  return [
    for (final group in grouped)
      ConversationMapGroup(
        latitude: group.anchor.latitude,
        longitude: group.anchor.longitude,
        conversations: group.conversations,
      ),
  ];
}

/// Conversations by place: a static map preview of every cluster anchor (tap
/// opens the native map app) above a grouped list of the conversations recorded
/// at each place. Single-conversation places open the conversation directly;
/// multi-conversation places keep the cluster bottom sheet.
class ConversationMapPage extends StatelessWidget {
  const ConversationMapPage({super.key, required this.conversations});

  final List<ServerConversation> conversations;

  Future<void> _openConversation(BuildContext context, ServerConversation conversation) async {
    final timestamp = conversation.startedAt ?? conversation.createdAt;
    final day = conversationLocalDayKey(timestamp);
    context.read<ConversationDetailProvider>().updateConversation(conversation.id, day);
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => ConversationDetailPage(conversation: conversation)));
  }

  void _openGroup(BuildContext context, ConversationMapGroup group) {
    if (group.conversations.length == 1) {
      _openConversation(context, group.conversations.single);
      return;
    }
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppStyles.backgroundSecondary,
      builder: (sheetContext) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 8),
              child: Text(
                '${group.conversations.length} ${context.l10n.conversations}',
                style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600),
              ),
            ),
            for (final conversation in group.conversations)
              ListTile(
                key: ValueKey('conversation_map_cluster_row_${conversation.id}'),
                title: Text(
                  conversation.structured.title.isEmpty
                      ? context.l10n.untitledConversation
                      : conversation.structured.title,
                  style: const TextStyle(color: Colors.white),
                ),
                subtitle: Text(
                  (conversation.startedAt ?? conversation.createdAt).toLocal().toString(),
                  style: const TextStyle(color: Colors.white60),
                ),
                trailing: const Icon(Icons.chevron_right, color: Colors.white70),
                onTap: () {
                  Navigator.of(sheetContext).pop();
                  _openConversation(context, conversation);
                },
              ),
          ],
        ),
      ),
    );
  }

  String _groupLabel(BuildContext context, ConversationMapGroup group) {
    if (group.conversations.length == 1) {
      final conversation = group.conversations.single;
      return conversation.structured.title.isEmpty ? context.l10n.untitledConversation : conversation.structured.title;
    }
    return '${group.conversations.length} ${context.l10n.conversations}';
  }

  @override
  Widget build(BuildContext context) {
    final groups = buildConversationMapGroups(conversations);
    return Scaffold(
      backgroundColor: AppStyles.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: AppStyles.backgroundPrimary,
        foregroundColor: Colors.white,
        title: Text('${context.l10n.conversations} · ${context.l10n.location}'),
      ),
      body: groups.isEmpty
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Text(
                  conversations.isEmpty ? context.l10n.noConversationsYet : context.l10n.unknownLocation,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white70, fontSize: 16),
                ),
              ),
            )
          : ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
              children: [
                Semantics(
                  button: true,
                  label: '${context.l10n.conversations} · ${context.l10n.location}',
                  child: GestureDetector(
                    onTap: () => MapsUtil.launchMap(groups.first.latitude, groups.first.longitude),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(24),
                      child: SizedBox(
                        key: const ValueKey('conversation_map_preview'),
                        height: 220,
                        child: OmiMapPreview(
                          key: ValueKey('conversation_map_preview_${groups.length}'),
                          pins: [
                            for (final group in groups) OmiMapPin(latitude: group.latitude, longitude: group.longitude),
                          ],
                          backgroundColor: AppStyles.backgroundPrimary,
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                for (final group in groups)
                  Semantics(
                    // The established per-place tappable key (this was the
                    // marker's); kept stable for automation that predates the
                    // static preview.
                    key: ValueKey('conversation_map_marker_${group.membershipKey}'),
                    button: true,
                    label: _groupLabel(context, group),
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => _openGroup(context, group),
                      child: Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        decoration: BoxDecoration(
                          color: AppStyles.backgroundSecondary,
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Row(
                          children: [
                            Container(
                              width: 36,
                              height: 36,
                              decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                              child: Center(
                                child: group.conversations.length == 1
                                    ? const Icon(Icons.location_on, color: Colors.black, size: 20)
                                    : Text(
                                        '${group.conversations.length}',
                                        style: const TextStyle(
                                          color: Colors.black,
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Text(
                                _groupLabel(context, group),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                              ),
                            ),
                            const Icon(Icons.chevron_right, color: Colors.white70),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
    );
  }
}
