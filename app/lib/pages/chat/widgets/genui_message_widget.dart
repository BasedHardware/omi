import 'dart:async';

import 'package:flutter/material.dart';

import 'package:flutter_map/flutter_map.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/chat/widgets/genui_message_parser.dart';
import 'package:omi/pages/conversation_detail/maps_util.dart';

class GenUiMessageWidget extends StatefulWidget {
  final GenUiMessageCard card;
  final FutureOr<void> Function(String message) onSubmitMessage;

  const GenUiMessageWidget({super.key, required this.card, required this.onSubmitMessage});

  @override
  State<GenUiMessageWidget> createState() => _GenUiMessageWidgetState();
}

class _GenUiMessageWidgetState extends State<GenUiMessageWidget> {
  bool _isRunningAction = false;

  Future<void> _handleAction(GenUiAction action) async {
    if (_isRunningAction) return;

    setState(() => _isRunningAction = true);
    try {
      switch (action.type) {
        case GenUiActionType.shareLocation:
          final serviceEnabled = await Geolocator.isLocationServiceEnabled();
          if (!serviceEnabled) {
            throw Exception('Location services are disabled.');
          }

          var permission = await Geolocator.checkPermission();
          if (permission == LocationPermission.denied) {
            permission = await Geolocator.requestPermission();
          }
          if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
            throw Exception('Location permission was not granted.');
          }

          final position = await Geolocator.getCurrentPosition();
          await widget.onSubmitMessage(
            'My current location is latitude ${position.latitude}, longitude ${position.longitude}.',
          );
          break;
        case GenUiActionType.openMap:
          if (widget.card.latitude != null && widget.card.longitude != null) {
            MapsUtil.launchMap(widget.card.latitude!, widget.card.longitude!);
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
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', '')), backgroundColor: Colors.red),
      );
    } finally {
      if (mounted) {
        setState(() => _isRunningAction = false);
      }
    }
  }

  Widget _buildMapPreview() {
    final latitude = widget.card.latitude;
    final longitude = widget.card.longitude;
    if (latitude == null || longitude == null) return const SizedBox.shrink();

    return ClipRRect(
      borderRadius: BorderRadius.circular(18),
      child: GestureDetector(
        onTap: () => MapsUtil.launchMap(latitude, longitude),
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
            widget.card.title,
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
                return ElevatedButton.icon(
                  onPressed: _isRunningAction ? null : () => _handleAction(action),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.deepPurpleAccent,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  ),
                  icon: _isRunningAction
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
                  label: Text(action.label),
                );
              }).toList(),
            ),
          ],
        ],
      ),
    );
  }
}
