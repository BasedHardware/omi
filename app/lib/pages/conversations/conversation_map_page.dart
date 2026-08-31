import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/ui_guidelines.dart';

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

class ConversationMapPage extends StatefulWidget {
  const ConversationMapPage({super.key, required this.conversations, this.tileProvider});

  final List<ServerConversation> conversations;
  final TileProvider? tileProvider;

  @override
  State<ConversationMapPage> createState() => _ConversationMapPageState();
}

class _ConversationMapPageState extends State<ConversationMapPage> {
  static const double _tileLoadZoomDelta = 0.000001;
  final MapController _mapController = MapController();

  @override
  void dispose() {
    _mapController.dispose();
    super.dispose();
  }

  void _loadTilesAfterLayout() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final camera = _mapController.camera;
      // flutter_map 7 can apply the initial camera fit after creating its first
      // tile set without scheduling the newly visible tiles to load.
      _mapController.move(camera.center, camera.zoom + _tileLoadZoomDelta);
    });
  }

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

  @override
  Widget build(BuildContext context) {
    final groups = buildConversationMapGroups(widget.conversations);
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
                  widget.conversations.isEmpty ? context.l10n.noConversationsYet : context.l10n.unknownLocation,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white70, fontSize: 16),
                ),
              ),
            )
          : FlutterMap(
              mapController: _mapController,
              options: MapOptions(
                initialCenter: LatLng(groups.first.latitude, groups.first.longitude),
                initialZoom: groups.length == 1 ? 14 : 11,
                initialCameraFit: groups.length == 1
                    ? null
                    : CameraFit.bounds(
                        bounds: LatLngBounds.fromPoints(
                          groups.map((group) => LatLng(group.latitude, group.longitude)).toList(),
                        ),
                        padding: const EdgeInsets.all(48),
                      ),
                backgroundColor: AppStyles.backgroundPrimary,
                onMapReady: _loadTilesAfterLayout,
              ),
              children: [
                TileLayer(
                  urlTemplate: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
                  subdomains: const ['a', 'b', 'c', 'd'],
                  userAgentPackageName: 'me.omi.app',
                  retinaMode: RetinaMode.isHighDensity(context),
                  tileProvider: widget.tileProvider,
                ),
                MarkerLayer(
                  markers: [
                    for (final group in groups)
                      Marker(
                        point: LatLng(group.latitude, group.longitude),
                        width: 44,
                        height: 44,
                        child: Semantics(
                          button: true,
                          label: group.conversations.length == 1
                              ? (group.conversations.single.structured.title.isEmpty
                                  ? context.l10n.untitledConversation
                                  : group.conversations.single.structured.title)
                              : '${group.conversations.length} ${context.l10n.conversations}',
                          child: GestureDetector(
                            key: ValueKey('conversation_map_marker_${group.membershipKey}'),
                            onTap: () => _openGroup(context, group),
                            child: Container(
                              decoration: BoxDecoration(
                                color: Colors.white,
                                shape: BoxShape.circle,
                                border: Border.all(color: Colors.black, width: 2),
                                boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 8)],
                              ),
                              alignment: Alignment.center,
                              child: group.conversations.length == 1
                                  ? const Icon(Icons.location_on, color: Colors.black, size: 24)
                                  : Text(
                                      '${group.conversations.length}',
                                      style: const TextStyle(color: Colors.black, fontWeight: FontWeight.w700),
                                    ),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ],
            ),
    );
  }
}
