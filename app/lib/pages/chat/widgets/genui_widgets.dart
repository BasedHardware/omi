import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/pages/conversation_detail/maps_util.dart';

class GenUiBlocksWidget extends StatelessWidget {
  final List<GenUiBlock> blocks;
  final Function(String) sendMessage;

  const GenUiBlocksWidget({super.key, required this.blocks, required this.sendMessage});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: blocks.map((block) {
        switch (block.type) {
          case GenUiBlockType.map:
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
              child: MapCardWidget(props: block.props),
            );
          case GenUiBlockType.actionButtons:
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
              child: ActionButtonsWidget(props: block.props, sendMessage: sendMessage),
            );
        }
      }).toList(),
    );
  }
}

class MapCardWidget extends StatelessWidget {
  final Map<String, dynamic> props;

  const MapCardWidget({super.key, required this.props});

  @override
  Widget build(BuildContext context) {
    final lat = (props['latitude'] as num?)?.toDouble();
    final lng = (props['longitude'] as num?)?.toDouble();
    final title = props['title'] as String? ?? '';
    final description = props['description'] as String?;
    final zoom = (props['zoom'] as num?)?.toInt() ?? 15;

    if (lat == null || lng == null) return const SizedBox.shrink();

    final mapImageUrl = MapsUtil.getMapImageUrl(lat, lng, zoom: zoom);

    return GestureDetector(
      onTap: () async {
        try {
          await MapsUtil.launchMap(lat, lng);
        } catch (_) {
          if (!context.mounted) return;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(context.l10n.couldNotOpenUrl)),
          );
        }
      },
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF1A1A20),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (title.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
                child: Row(
                  children: [
                    const Icon(Icons.location_on, color: Color(0xFF9C27B0), size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        title,
                        style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
            SizedBox(
              height: 160,
              width: double.infinity,
              child: CachedNetworkImage(
                imageUrl: mapImageUrl,
                fit: BoxFit.cover,
                placeholder: (context, url) => Container(
                  color: const Color(0xFF0E1626),
                  child: const Center(child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white24)),
                ),
                errorWidget: (context, url, error) => Container(
                  color: const Color(0xFF0E1626),
                  child: const Center(
                    child: Icon(Icons.map_outlined, color: Colors.white24, size: 48),
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (description != null && description.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(
                        description,
                        style: TextStyle(color: Colors.grey.shade400, fontSize: 13, height: 1.3),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  Row(
                    children: [
                      Icon(Icons.open_in_new, color: Colors.grey.shade500, size: 14),
                      const SizedBox(width: 4),
                      Text(
                        context.l10n.tapToOpenInMaps,
                        style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ActionButtonsWidget extends StatelessWidget {
  final Map<String, dynamic> props;
  final Function(String) sendMessage;

  const ActionButtonsWidget({super.key, required this.props, required this.sendMessage});

  @override
  Widget build(BuildContext context) {
    final title = props['title'] as String?;
    final buttons = ((props['buttons'] ?? []) as List<dynamic>).map((b) => b.toString()).toList();

    if (buttons.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (title != null && title.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              title,
              style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500),
            ),
          ),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: buttons.map((label) {
            return GestureDetector(
              onTap: () => sendMessage(label),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
                ),
                child: Text(
                  label,
                  style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w400),
                ),
              ),
            );
          }).toList(),
        ),
      ],
    );
  }
}
