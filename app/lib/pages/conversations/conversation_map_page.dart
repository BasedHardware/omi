import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/maps_util.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart' show ConversationUntitledRenderedSurface;
import 'package:omi/utils/conversations/conversation_title.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/native_static_map.dart';
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
  const ConversationMapPage({super.key, required this.conversations, this.launchMap, this.staticMapResolver});

  final List<ServerConversation> conversations;

  /// Opens a place in the map app; [MapsUtil.launchMap] unless a test injects a launcher.
  @visibleForTesting
  final void Function(double latitude, double longitude)? launchMap;

  /// Fetches the native preview's map file; [resolveNativeStaticMapFile] unless a test injects one.
  @visibleForTesting
  final NativeStaticMapResolver? staticMapResolver;

  void _launch(double latitude, double longitude) => (launchMap ?? MapsUtil.launchMap)(latitude, longitude);

  Future<void> _openConversation(BuildContext context, ServerConversation conversation) async {
    final timestamp = conversation.startedAt ?? conversation.createdAt;
    final day = conversationLocalDayKey(timestamp);
    context.read<ConversationDetailProvider>().updateConversation(conversation.id, day);
    await routeToPage(context, ConversationDetailPage(conversation: conversation));
  }

  void _openGroup(BuildContext context, ConversationMapGroup group) {
    if (group.conversations.length == 1) {
      _openConversation(context, group.conversations.single);
      return;
    }
    final title = context.l10n.conversationCount(group.conversations.length);
    showOmiSheet<void>(
      context: context,
      title: title,
      padding: EdgeInsets.zero,
      builder: (sheetContext) => _clusterList(context, sheetContext, group),
      nativeBuilder: (sheetContext) => ConversationMapClusterChooser(
        title: title,
        conversations: group.conversations,
        onOpen: (conversation) => _openConversation(context, conversation),
        fallback: OmiSheetScaffold(
          title: title,
          padding: EdgeInsets.zero,
          child: _clusterList(context, sheetContext, group),
        ),
      ),
    );
  }

  Widget _clusterList(BuildContext context, BuildContext sheetContext, ConversationMapGroup group) {
    final dates = OmiDateFormat.of(context);
    return ListView(
      shrinkWrap: true,
      children: [
        for (final conversation in group.conversations)
          ListTile(
            key: ValueKey('conversation_map_cluster_row_${conversation.id}'),
            title: Text(
              conversationDisplayTitle(
                conversation,
                context.l10n,
                surface: ConversationUntitledRenderedSurface.map,
                dates: OmiDateFormat.of(context),
              ),
            ),
            subtitle: Text(
              dates.dateTime(conversation.startedAt ?? conversation.createdAt),
              style: TextStyle(color: OmiColors.textSecondary),
            ),
            trailing: Icon(Icons.chevron_right, color: OmiColors.textTertiary),
            onTap: () {
              Navigator.of(sheetContext).pop();
              _openConversation(context, conversation);
            },
          ),
      ],
    );
  }

  String _groupLabel(BuildContext context, ConversationMapGroup group) {
    if (group.conversations.length == 1) {
      final conversation = group.conversations.single;
      return conversationDisplayTitle(
        conversation,
        context.l10n,
        surface: ConversationUntitledRenderedSurface.map,
        dates: OmiDateFormat.of(context),
      );
    }
    return context.l10n.conversationCount(group.conversations.length);
  }

  @override
  Widget build(BuildContext context) {
    final groups = buildConversationMapGroups(conversations);
    final classic = Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.conversationMap)),
      body: groups.isEmpty
          ? OmiEmptyState(
              icon: Icons.map_outlined,
              title: conversations.isEmpty ? context.l10n.noConversationsYet : context.l10n.unknownLocation,
            )
          : ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
              children: [
                Semantics(
                  button: true,
                  label: context.l10n.conversationMap,
                  child: GestureDetector(
                    onTap: () => _launch(groups.first.latitude, groups.first.longitude),
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
                          backgroundColor: OmiColors.surface0,
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
                        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(16)),
                        child: Row(
                          children: [
                            Container(
                              width: 36,
                              height: 36,
                              decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
                              child: Center(
                                child: group.conversations.length == 1
                                    ? Icon(Icons.location_on, color: OmiColors.onAccent, size: 20)
                                    : Text(
                                        '${group.conversations.length}',
                                        style: TextStyle(color: OmiColors.onAccent, fontWeight: FontWeight.w700),
                                      ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Text(
                                _groupLabel(context, group),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  color: OmiColors.textPrimary,
                                  fontSize: 15,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                            Icon(Icons.chevron_right, color: OmiColors.textSecondary),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
    );
    if (!nativePresentationEnabled) return classic;
    return _NativeConversationMap(page: this, groups: groups, classic: classic);
  }
}

/// The native title of a place's conversation. Locked content never crosses the bridge, so a
/// locked conversation shows the generic label instead of its title.
String _nativeConversationTitle(BuildContext context, ServerConversation conversation) => conversation.isLocked
    ? context.l10n.conversations
    : conversationDisplayTitle(
        conversation,
        context.l10n,
        surface: ConversationUntitledRenderedSurface.map,
        dates: OmiDateFormat.of(context),
      );

/// The same map, Open in Maps and grouped places, projected natively. The preview is a temporary
/// PNG fetched by Dart through the authenticated proxy; this State owns that file and deletes it on
/// dispose, on a brightness or session change and when a fetch completes too late. Rows address
/// groups by index; only Dart maps an index back to its conversations.
class _NativeConversationMap extends StatefulWidget {
  const _NativeConversationMap({required this.page, required this.groups, required this.classic});

  final ConversationMapPage page;
  final List<ConversationMapGroup> groups;
  final Widget classic;

  @override
  State<_NativeConversationMap> createState() => _NativeConversationMapState();
}

class _NativeConversationMapState extends State<_NativeConversationMap> {
  late final Future<bool> _support = supportsNativePresentation();

  /// Created only once native presentation is confirmed, so an unsupported device never fetches,
  /// encodes or writes the hidden map file.
  NativeStaticMap? _staticMap;

  @override
  void dispose() {
    _staticMap?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<bool>(
      future: _support,
      builder: (context, support) {
        if (support.connectionState != ConnectionState.done) return const OmiLoadingState();
        if (support.data != true) return widget.classic;
        return _native(context);
      },
    );
  }

  Widget _native(BuildContext context) {
    final map = _staticMap ??= NativeStaticMap(resolver: widget.page.staticMapResolver);
    final groups = widget.groups;
    // Rebuilds on a theme change, so a new map in the other style replaces the current file.
    Theme.of(context);
    final width = (MediaQuery.sizeOf(context).width - 32).round();
    if (groups.isNotEmpty && width > 0) {
      map.show(
        pins: [for (final group in groups) OmiMapPin(latitude: group.latitude, longitude: group.longitude)],
        width: width,
        height: 220,
        brightness: OmiColors.active == OmiPalette.light ? Brightness.light : Brightness.dark,
      );
    }
    return ListenableBuilder(listenable: map, builder: (context, _) => _surface(context, map, groups));
  }

  Widget _surface(BuildContext context, NativeStaticMap map, List<ConversationMapGroup> groups) {
    final l10n = context.l10n;
    final page = widget.page;
    return IosNativeSurface(
      title: l10n.conversationMap,
      fallback: widget.classic,
      empty: page.conversations.isEmpty ? l10n.noConversationsYet : l10n.unknownLocation,
      toolbar: [
        NativeRow('conversation_map_back', l10n.back,
            symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        if (groups.isNotEmpty) ...[
          NativeSection('conversation_map_preview', [
            if (map.uri != null)
              NativeRow('conversation_map_image', l10n.conversationMap,
                  kind: 'image', imageUri: map.uri, maximumValue: 4),
            if (map.loading) NativeRow('conversation_map_loading', l10n.loading, kind: 'label'),
            if (map.failed) NativeRow('conversation_map_error', l10n.couldNotLoadMap, kind: 'label'),
            NativeRow('conversation_map_open', l10n.openInMaps,
                symbol: 'map', action: (_) => page._launch(groups.first.latitude, groups.first.longitude)),
          ]),
          NativeSection('conversation_map_groups', [
            for (final (index, group) in groups.indexed)
              NativeRow(
                'conversation_map_group_$index',
                group.conversations.length == 1
                    ? _nativeConversationTitle(context, group.conversations.single)
                    : l10n.conversationCount(group.conversations.length),
                kind: 'navigation',
                symbol: group.conversations.length == 1 ? 'mappin.circle.fill' : 'square.stack',
                action: (_) => page._openGroup(context, group),
              ),
          ]),
        ],
      ],
    );
  }
}

/// The native chooser for a place with several conversations. Choosing one closes the sheet and
/// then opens it, only while the account session that opened the chooser is still current.
class ConversationMapClusterChooser extends StatefulWidget {
  const ConversationMapClusterChooser({
    super.key,
    required this.title,
    required this.conversations,
    required this.onOpen,
    required this.fallback,
  });

  final String title;
  final List<ServerConversation> conversations;
  final void Function(ServerConversation conversation) onOpen;

  /// The complete Flutter chooser, already inside its sheet scaffold.
  final Widget fallback;

  @override
  State<ConversationMapClusterChooser> createState() => _ConversationMapClusterChooserState();
}

class _ConversationMapClusterChooserState extends State<ConversationMapClusterChooser> {
  final _owner = AuthService.instance.captureSessionSnapshot();
  bool _chosen = false;

  void _choose(ServerConversation conversation) {
    // A second command before the sheet closes must not pop the map beneath it.
    if (_chosen) return;
    _chosen = true;
    final owner = _owner;
    Navigator.of(context).pop();
    if (owner == null || !AuthService.instance.isSessionSnapshotCurrent(owner)) return;
    widget.onOpen(conversation);
  }

  @override
  Widget build(BuildContext context) {
    final dates = OmiDateFormat.of(context);
    return IosNativeSurface(
      title: widget.title,
      fallback: widget.fallback,
      toolbar: [
        NativeRow('conversation_map_cluster_close', context.l10n.close,
            symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        NativeSection('conversation_map_cluster', [
          for (final (index, conversation) in widget.conversations.indexed)
            NativeRow(
              'conversation_map_cluster_$index',
              _nativeConversationTitle(context, conversation),
              subtitle: dates.dateTime(conversation.startedAt ?? conversation.createdAt),
              kind: 'navigation',
              action: (_) => _choose(conversation),
            ),
        ]),
      ],
    );
  }
}
