import 'package:flutter/material.dart';

import 'package:geolocator/geolocator.dart';
import 'package:map_launcher/map_launcher.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/models/genui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

class GenUiMessageWidget extends StatelessWidget {
  final GenUiPayload payload;
  final void Function(String) sendMessage;

  const GenUiMessageWidget({
    super.key,
    required this.payload,
    required this.sendMessage,
  });

  @override
  Widget build(BuildContext context) {
    return _buildNode(context, payload.root);
  }

  Widget _buildNode(BuildContext context, GenUiNode node) {
    switch (node.type) {
      case GenUiNodeType.column:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: _buildChildren(context, node.children),
        );
      case GenUiNodeType.row:
        return Wrap(
          spacing: 8,
          runSpacing: 8,
          children: _buildChildren(context, node.children),
        );
      case GenUiNodeType.text:
        if (node.text == null || node.text!.isEmpty) {
          return const SizedBox.shrink();
        }
        return Text(
          node.text!,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                fontSize: 16,
                height: 1.4,
                color: Colors.white,
              ),
        );
      case GenUiNodeType.button:
        if (node.text == null || node.text!.isEmpty) {
          return const SizedBox.shrink();
        }
        return SizedBox(
          height: 40,
          child: ElevatedButton(
            onPressed: node.action == null ? null : () => _handleAction(context, node.action!),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            child: Text(node.text!),
          ),
        );
      case GenUiNodeType.mapCard:
        return _buildMapCard(context, node);
    }
  }

  List<Widget> _buildChildren(BuildContext context, List<GenUiNode> children) {
    return children
        .map((child) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _buildNode(context, child),
            ))
        .toList();
  }

  Widget _buildMapCard(BuildContext context, GenUiNode node) {
    final mapCard = node.mapCard;
    if (mapCard == null) {
      return const SizedBox.shrink();
    }

    final title = mapCard.title ?? context.l10n.genUiMapDefaultTitle;
    final subtitle = mapCard.subtitle;
    final actionLabel = mapCard.actionLabel ?? context.l10n.genUiOpenMap;
    final action = node.action ??
        GenUiAction(
          type: 'open_map',
          payload: {
            'latitude': mapCard.latitude,
            'longitude': mapCard.longitude,
            'url': mapCard.url,
          },
        );

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.place, color: Colors.white70),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(color: Colors.white),
                    ),
                    if (subtitle != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          subtitle,
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.white70),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => _handleAction(context, action),
              icon: const Icon(Icons.map_outlined, size: 18),
              label: Text(actionLabel),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _handleAction(BuildContext context, GenUiAction action) async {
    switch (action.type) {
      case 'share_location':
        await _handleShareLocation(context);
        break;
      case 'open_map':
        await _handleOpenMap(context, action.payload);
        break;
      case 'open_url':
        await _handleOpenUrl(context, action.payload);
        break;
      case 'send_message':
        final text = action.payload['text']?.toString();
        if (text != null && text.isNotEmpty) {
          sendMessage(text);
        }
        break;
      default:
        Logger.debug('Unsupported GenUI action: ${action.type}');
    }
  }

  Future<void> _handleShareLocation(BuildContext context) async {
    final l10n = context.l10n;
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        await _showLocationServiceDisabled(context);
        return;
      }

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }

      if (permission == LocationPermission.denied) {
        _showSnackBar(context, l10n.genUiLocationPermissionDenied);
        return;
      }

      if (permission == LocationPermission.deniedForever) {
        _showSnackBar(context, l10n.genUiLocationPermissionPermanentlyDenied);
        return;
      }

      final position = await Geolocator.getCurrentPosition();
      await updateUserGeolocation(
        geolocation: Geolocation(
          latitude: position.latitude,
          longitude: position.longitude,
          accuracy: position.accuracy,
          altitude: position.altitude,
          time: position.timestamp.toUtc(),
        ),
      );

      sendMessage(
        l10n.genUiLocationSharedMessage(position.latitude.toStringAsFixed(6), position.longitude.toStringAsFixed(6)),
      );
    } catch (e) {
      Logger.error('Failed to share location: $e');
      _showSnackBar(context, l10n.genUiShareLocationFailed);
    }
  }

  Future<void> _handleOpenMap(BuildContext context, Map<String, dynamic> payload) async {
    final l10n = context.l10n;
    try {
      final latitude = payload['latitude'] ?? payload['lat'];
      final longitude = payload['longitude'] ?? payload['lng'];
      final url = payload['url']?.toString();
      if (latitude is num && longitude is num) {
        final coords = Coords(latitude.toDouble(), longitude.toDouble());
        final maps = await MapLauncher.installedMaps;
        if (maps.isNotEmpty) {
          await maps.first.showMarker(
            coords: coords,
            title: payload['title']?.toString() ?? l10n.genUiMapDefaultTitle,
          );
          return;
        }
      }

      if (url != null && url.isNotEmpty) {
        final uri = Uri.parse(url);
        if (await canLaunchUrl(uri)) {
          await launchUrl(uri, mode: LaunchMode.externalApplication);
          return;
        }
      }

      _showSnackBar(context, l10n.genUiMapOpenFailed);
    } catch (e) {
      Logger.error('Failed to open map: $e');
      _showSnackBar(context, l10n.genUiMapOpenFailed);
    }
  }

  Future<void> _handleOpenUrl(BuildContext context, Map<String, dynamic> payload) async {
    final l10n = context.l10n;
    final url = payload['url']?.toString();
    if (url == null || url.isEmpty) {
      _showSnackBar(context, l10n.genUiMapOpenFailed);
      return;
    }

    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } else {
      _showSnackBar(context, l10n.genUiMapOpenFailed);
    }
  }

  Future<void> _showLocationServiceDisabled(BuildContext context) async {
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(context.l10n.locationServiceDisabled),
        content: Text(context.l10n.locationServiceDisabledDesc),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(context.l10n.cancel),
          ),
        ],
      ),
    );
  }

  void _showSnackBar(BuildContext context, String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
      ),
    );
  }
}
