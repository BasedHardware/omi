import 'dart:math' as math;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

/// Resolves the Authorization header for proxy image requests. Injectable so
/// tests can control when the header arrives (or never does).
typedef OmiMapAuthHeaderResolver = Future<String?> Function();

/// A single map pin coordinate rendered by [OmiMapPreview].
class OmiMapPin {
  const OmiMapPin({required this.latitude, required this.longitude});

  final double latitude;
  final double longitude;
}

/// Maximum pins the backend static-map route accepts after de-duplication.
const int kOmiMapPreviewMaxPins = 50;

/// Builds the URL for the backend's authed static-map proxy (`GET /v1/static-map`).
///
/// Every in-app map preview funnels through this builder and [OmiMapPreview], so
/// a future provider swap touches this file and `backend/utils/static_map.py`
/// only. Pins are quantized to four decimals to match the server's cache
/// quantization (~11m), which makes repeat renders of the same place a cache
/// hit for every user.
String buildOmiStaticMapUrl({required List<OmiMapPin> pins, required int width, required int height}) {
  // Quantize to four decimals to match the server's cache quantization (~11m),
  // which makes repeat renders of the same place a cache hit for every user;
  // drop pins that quantize onto an already-included one.
  final seen = <String>{};
  final parts = <String>[];
  for (final pin in pins) {
    if (parts.length >= kOmiMapPreviewMaxPins) break;
    final value = '${pin.latitude.toStringAsFixed(4)},${pin.longitude.toStringAsFixed(4)}';
    if (seen.add(value)) parts.add(value);
  }
  return '${Env.apiBaseUrl}v1/static-map?pins=${Uri.encodeQueryComponent(parts.join('|'))}&width=$width&height=$height';
}

/// The one map preview surface in the app: a dark static-map image fetched from
/// the backend proxy, falling back to a deterministic dark canvas with pin dots
/// while loading, offline, or whenever the image cannot be rendered — it never
/// shows an error state.
///
/// The preview is non-interactive by design; wrap it in a GestureDetector that
/// hands off to `MapsUtil.launchMap` (native map app) for interaction.
class OmiMapPreview extends StatefulWidget {
  const OmiMapPreview({
    super.key,
    required this.pins,
    this.backgroundColor = const Color(0xFF1A1A1F),
    this.imageUrl,
    this.authHeaderProvider,
  });

  final List<OmiMapPin> pins;

  /// Canvas color used for the loading/fallback render and image letterboxing.
  final Color backgroundColor;

  /// Pre-built image URL. Tests use this to avoid the network; production
  /// callers leave it null so [buildOmiStaticMapUrl] builds the proxy URL.
  /// An explicit URL skips the auth gate (headers are optional for it).
  final String? imageUrl;

  /// How the session's Authorization header is resolved. Tests inject a
  /// controllable future; production uses [getAuthHeader].
  final OmiMapAuthHeaderResolver? authHeaderProvider;

  @override
  State<OmiMapPreview> createState() => _OmiMapPreviewState();
}

class _OmiMapPreviewState extends State<OmiMapPreview> {
  String? _authHeader;

  @override
  void initState() {
    super.initState();
    _resolveAuthHeader();
  }

  Future<void> _resolveAuthHeader() async {
    String? header;
    try {
      header = await (widget.authHeaderProvider ?? getAuthHeader)();
    } catch (_) {
      header = null; // offline/unauthenticated: fall back to the canvas below
    }
    if (!mounted || header == _authHeader) return;
    setState(() => _authHeader = header);
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final fallback = _PinDotsCanvas(pins: widget.pins, color: widget.backgroundColor);
        final width = constraints.maxWidth;
        final height = constraints.maxHeight;
        if (widget.pins.isEmpty || !width.isFinite || !height.isFinite || width <= 0 || height <= 0) {
          return fallback;
        }
        final url = widget.imageUrl;
        if (url != null) {
          return _image(url: url, width: width, height: height, fallback: fallback, authRequired: false);
        }
        // The proxy request carries the session token; firing it before the
        // header resolves would 401, and the URL-derived image cache key would
        // never re-fetch once the header arrives. The pin-dot canvas (which
        // already doubles as the error/offline render) holds the frame until
        // the header resolves.
        if (_authHeader == null) {
          return fallback;
        }
        return _image(
          url: buildOmiStaticMapUrl(pins: widget.pins, width: width.round(), height: height.round()),
          width: width,
          height: height,
          fallback: fallback,
          authRequired: true,
        );
      },
    );
  }

  Widget _image({
    required String url,
    required double width,
    required double height,
    required Widget fallback,
    required bool authRequired,
  }) {
    return CachedNetworkImage(
      key: ValueKey(url),
      imageUrl: url,
      httpHeaders: {if (authRequired) 'Authorization': _authHeader!},
      fit: BoxFit.cover,
      width: width,
      height: height,
      placeholder: (_, __) => fallback,
      errorWidget: (_, __, ___) => fallback,
    );
  }
}

/// Deterministic, offline-safe map placeholder: a plain dark canvas with one
/// white dot per pin, placed by normalizing the pins' bounding box into the
/// available box. Never looks broken; identical pins always paint identically.
class _PinDotsCanvas extends StatelessWidget {
  const _PinDotsCanvas({required this.pins, required this.color});

  final List<OmiMapPin> pins;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      key: const ValueKey('omi_map_preview_fallback'),
      size: Size.infinite,
      painter: _PinDotsPainter(pins: pins, color: color),
    );
  }
}

class _PinDotsPainter extends CustomPainter {
  _PinDotsPainter({required this.pins, required this.color});

  final List<OmiMapPin> pins;
  final Color color;

  static const double _padding = 20;
  static const double _dotRadius = 4;

  @override
  void paint(Canvas canvas, Size size) {
    final background = Paint()..color = color;
    canvas.drawRect(Offset.zero & size, background);
    if (pins.isEmpty || size.isEmpty) return;

    var minLat = pins.first.latitude;
    var maxLat = minLat;
    var minLng = pins.first.longitude;
    var maxLng = minLng;
    for (final pin in pins) {
      minLat = math.min(minLat, pin.latitude);
      maxLat = math.max(maxLat, pin.latitude);
      minLng = math.min(minLng, pin.longitude);
      maxLng = math.max(maxLng, pin.longitude);
    }

    final usable = Size(math.max(size.width - 2 * _padding, 1), math.max(size.height - 2 * _padding, 1));
    // Equirectangular placement — good enough for dot positions at city scale
    // (the static image carries the real projection). Longitude degrees are
    // compressed by cos(latitude).
    final latSpan = maxLat - minLat;
    final lngSpan = maxLng - minLng;
    final centerLat = (minLat + maxLat) / 2;
    final centerLng = (minLng + maxLng) / 2;
    final latCos = math.max(math.cos(centerLat * math.pi / 180).abs(), 0.01);
    final lngSpanProjected = lngSpan * latCos;

    // Uniform scale that fits both spans inside the usable box; a span of zero
    // on one axis collapses it to the center line. A single pin (both spans
    // zero) scales to 0 and lands exactly at the center.
    final double scale;
    if (lngSpanProjected <= 0 && latSpan <= 0) {
      scale = 0;
    } else if (lngSpanProjected <= 0) {
      scale = usable.height / latSpan;
    } else if (latSpan <= 0) {
      scale = usable.width / lngSpanProjected;
    } else {
      scale = math.min(usable.width / lngSpanProjected, usable.height / latSpan);
    }

    final dot = Paint()..color = Colors.white;
    final outline = Paint()
      ..color = Colors.black
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    final center = Offset(size.width / 2, size.height / 2);
    for (final pin in pins) {
      final position =
          center + Offset((pin.longitude - centerLng) * latCos * scale, -(pin.latitude - centerLat) * scale);
      canvas.drawCircle(position, _dotRadius, dot);
      canvas.drawCircle(position, _dotRadius, outline);
    }
  }

  @override
  bool shouldRepaint(_PinDotsPainter oldDelegate) =>
      oldDelegate.pins.length != pins.length || oldDelegate.color != color || !_samePins(oldDelegate.pins);

  bool _samePins(List<OmiMapPin> other) {
    for (var i = 0; i < pins.length; i++) {
      if (pins[i].latitude != other[i].latitude || pins[i].longitude != other[i].longitude) return false;
    }
    return true;
  }
}
