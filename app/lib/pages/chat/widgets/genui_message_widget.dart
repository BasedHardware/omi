import 'dart:async';

import 'package:flutter/material.dart';

import 'package:flutter_map/flutter_map.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/chat/widgets/genui_message_parser.dart';
import 'package:omi/pages/conversation_detail/maps_util.dart';
import 'package:omi/utils/l10n_extensions.dart';

class GenUiMessageWidget extends StatefulWidget {
  final GenUiMessageCard card;
  final FutureOr<void> Function(String message) onSubmitMessage;

  const GenUiMessageWidget({super.key, required this.card, required this.onSubmitMessage});

  @override
  State<GenUiMessageWidget> createState() => _GenUiMessageWidgetState();
}

class _GenUiMessageWidgetState extends State<GenUiMessageWidget> {
  final Set<String> _runningActions = <String>{};

  String _actionKey(GenUiAction action) => '${action.type.name}:${action.label}:${action.url ?? ''}';

  Future<void> _showActionError(Object error) async {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(error.toString().replaceFirst('Exception: ', '')), backgroundColor: Colors.red),
    );
  }

  String _resolvedCardTitle(BuildContext context) {
    if (widget.card.title.trim().isNotEmpty) {
      return widget.card.title;
    }

    return switch (widget.card.type) {
      GenUiCardType.locationRequest => context.l10n.locationAccess,
      GenUiCardType.locationResult => context.l10n.locationAccess,
      GenUiCardType.info => context.l10n.open,
    };
  }

  String _resolvedActionLabel(BuildContext context, GenUiAction action) {
    if (action.label.trim().isNotEmpty) {
      return action.label;
    }

    return switch (action.type) {
      GenUiActionType.shareLocation => context.l10n.share,
      GenUiActionType.openMap => context.l10n.open,
      GenUiActionType.openUrl => context.l10n.open,
    };
  }

  Future<void> _handleAction(GenUiAction action) async {
    final actionKey = _actionKey(action);
    if (_runningActions.contains(actionKey)) return;

    setState(() => _runningActions.add(actionKey));
    try {
      switch (action.type) {
        case GenUiActionType.shareLocation:
          final serviceEnabled = await Geolocator.isLocationServiceEnabled();
          if (!serviceEnabled) {
            throw Exception(context.l10n.locationServiceDisabled);
          }

          var permission = await Geolocator.checkPermission();
          if (permission == LocationPermission.denied) {
            permission = await Geolocator.requestPermission();
          }
          if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
            throw Exception(context.l10n.backgroundLocationDenied);
          }

          final position = await Geolocator.getCurrentPosition();
          await widget.onSubmitMessage(
            'My current location is latitude ${position.latitude}, longitude ${position.longitude}.',
          );
          break;
        case GenUiActionType.openMap:
          if (widget.card.latitude != null && widget.card.longitude != null) {
            await MapsUtil.launchMap(widget.card.latitude!, widget.card.longitude!);
          }
          break;
        case GenUiActionType.openUrl:
          final url = action.url;
          if (url != null && url.isNotEmpty) {
            await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
          }
          break;
      }
    } catch (e) {
      await _showActionError(e);
    } finally {
      if (mounted) {
        setState(() => _runningActions.remove(actionKey));
      }
    }
  }

  Future<void> _handleMapPreviewTap(double latitude, double longitude) async {
    try {
      await MapsUtil.launchMap(latitude, longitude);
    } catch (e) {
      await _showActionError(e);
    }
  }

  Widget _buildMapPreview() {
    final latitude = widget.card.latitude;
    final longitude = widget.card.longitude;
    if (latitude == null || longitude == null) return const SizedBox.shrink();

    return ClipRRect(
      borderRadius: BorderRadius.circular(18),
      child: GestureDetector(
        onTap: () => _handleMapPreviewTap(latitude, longitude),
        child: SizedBox(
          width: double.infinity,
          height: 170,
          child: IgnorePointer(
            child: FlutterMap(
              options: MapOptions(
                initialCenter: LatLng(latitude, longitude),
                initialZoom: 14,
                interactionOptions: const InteractionOptions(flags: InteractiveFlag.none),
              ),
              children: [
                TileLayer(
                  urlTemplate: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
                  subdomains: const ['a', 'b', 'c', 'd'],
                  userAgentPackageName: 'me.omi.app',
                  retinaMode: true,
                ),
                MarkerLayer(
                  markers: [
                    Marker(
                      point: LatLng(latitude, longitude),
                      width: 32,
                      height: 32,
                      child: const FaIcon(FontAwesomeIcons.locationDot, color: Colors.deepPurpleAccent, size: 28),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _resolvedCardTitle(context),
            style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600),
          ),
          if ((widget.card.description ?? '').isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              widget.card.description!,
              style: TextStyle(color: Colors.grey.shade300, fontSize: 14, height: 1.4),
            ),
          ],
          if (widget.card.type == GenUiCardType.locationResult) ...[
            const SizedBox(height: 14),
            _buildMapPreview(),
          ],
          if (widget.card.actions.isNotEmpty) ...[
            const SizedBox(height: 14),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: widget.card.actions.map((action) {
                final isRunning = _runningActions.contains(_actionKey(action));
                return ElevatedButton.icon(
                  onPressed: isRunning ? null : () => _handleAction(action),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.deepPurpleAccent,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  ),
                  icon: isRunning
                      ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : Icon(
                          switch (action.type) {
                            GenUiActionType.shareLocation => Icons.my_location,
                            GenUiActionType.openMap => Icons.map_outlined,
                            GenUiActionType.openUrl => Icons.open_in_new,
                          },
                          size: 16,
                        ),
                  label: Text(_resolvedActionLabel(context, action)),
                );
              }).toList(),
            ),
          ],
        ],
      ),
    );
  }
}
