import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import '../models/highlight_data.dart';

/// Widget that displays highlighted text with a realistic marker effect.
/// Uses custom painting to create an organic, hand-drawn highlighter appearance.
/// Supports multi-line text with per-line highlight strokes.
class HighlightWidget extends StatelessWidget {
  final HighlightData data;

  const HighlightWidget({
    super.key,
    required this.data,
  });

  @override
  Widget build(BuildContext context) {
    return MarkerHighlight(
      color: data.color,
      child: Text(
        data.text,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 16,
          fontWeight: FontWeight.w500,
          height: 1.5,
        ),
      ),
    );
  }
}

/// A widget that wraps text with a realistic marker highlight effect.
/// Automatically detects multi-line text and paints separate strokes per line.
class MarkerHighlight extends StatefulWidget {
  final Widget child;
  final Color color;
  final double opacity;
  final double verticalPadding;
  final double horizontalPadding;

  const MarkerHighlight({
    super.key,
    required this.child,
    required this.color,
    this.opacity = 0.55,
    this.verticalPadding = 2.0,
    this.horizontalPadding = 4.0,
  });

  @override
  State<MarkerHighlight> createState() => _MarkerHighlightState();
}

class _MarkerHighlightState extends State<MarkerHighlight> {
  final GlobalKey _textKey = GlobalKey();
  List<Rect> _lineRects = [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _measureLines());
  }

  void _measureLines() {
    final renderObject = _textKey.currentContext?.findRenderObject();
    if (renderObject is RenderParagraph) {
      final boxes = _getTextBoxes(renderObject);
      if (boxes.isNotEmpty && mounted) {
        setState(() {
          _lineRects = boxes;
        });
      }
    } else if (renderObject is RenderBox) {
      // Fallback for non-paragraph render objects
      if (mounted) {
        setState(() {
          _lineRects = [Offset.zero & renderObject.size];
        });
      }
    }
  }

  List<Rect> _getTextBoxes(RenderParagraph paragraph) {
    final text = paragraph.text.toPlainText();
    if (text.isEmpty) return [];

    // Get selection boxes for the entire text - use tight width to match text only
    final boxes = paragraph.getBoxesForSelection(
      TextSelection(baseOffset: 0, extentOffset: text.length),
      boxHeightStyle: ui.BoxHeightStyle.strut,
      boxWidthStyle: ui.BoxWidthStyle.tight,
    );

    if (boxes.isEmpty) return [];

    // Group boxes by line (same top position = same line)
    final lineGroups = <double, List<TextBox>>{};
    for (final box in boxes) {
      final lineTop = (box.top / 2).round() * 2.0; // Round to group nearby tops
      lineGroups.putIfAbsent(lineTop, () => []).add(box);
    }

    // Convert to line rects
    return lineGroups.values.map((lineBoxes) {
      final left = lineBoxes.map((b) => b.left).reduce(math.min);
      final right = lineBoxes.map((b) => b.right).reduce(math.max);
      final top = lineBoxes.map((b) => b.top).reduce(math.min);
      final bottom = lineBoxes.map((b) => b.bottom).reduce(math.max);
      return Rect.fromLTRB(left, top, right, bottom);
    }).toList()
      ..sort((a, b) => a.top.compareTo(b.top));
  }

  @override
  void didUpdateWidget(MarkerHighlight oldWidget) {
    super.didUpdateWidget(oldWidget);
    WidgetsBinding.instance.addPostFrameCallback((_) => _measureLines());
  }

  @override
  Widget build(BuildContext context) {
    // TODO: Temporarily disabled highlight effect
    return widget.child;

    // return CustomPaint(
    //   painter: MultiLineMarkerPainter(
    //     lineRects: _lineRects,
    //     color: widget.color,
    //     opacity: widget.opacity,
    //     horizontalPadding: widget.horizontalPadding,
    //     verticalPadding: widget.verticalPadding,
    //   ),
    //   child: Padding(
    //     padding: EdgeInsets.symmetric(
    //       horizontal: widget.horizontalPadding,
    //       vertical: widget.verticalPadding,
    //     ),
    //     child: KeyedSubtree(
    //       key: _textKey,
    //       child: widget.child,
    //     ),
    //   ),
    // );
  }
}

/// Custom painter that draws realistic marker highlights for each line of text.
class MultiLineMarkerPainter extends CustomPainter {
  final List<Rect> lineRects;
  final Color color;
  final double opacity;
  final double horizontalPadding;
  final double verticalPadding;

  MultiLineMarkerPainter({
    required this.lineRects,
    required this.color,
    required this.opacity,
    required this.horizontalPadding,
    required this.verticalPadding,
  });

  @override
  void paint(Canvas canvas, Size size) {
    // Don't draw anything until we have actual line measurements
    // This prevents full-width highlights before text is measured
    if (lineRects.isEmpty) return;

    // Draw a marker stroke for each line with visible gap between them
    const lineGap = 3.0; // Visible gap between highlight strokes

    for (int i = 0; i < lineRects.length; i++) {
      final lineRect = lineRects[i];

      // Calculate the highlight height (thinner than the line to show gaps)
      final lineHeight = lineRect.bottom - lineRect.top;
      final highlightHeight = lineHeight - lineGap * 2;
      final centerY = lineRect.top + lineHeight / 2;

      // Create rect centered on the line with reduced height for gap
      // Only highlight the actual text width (plus small padding for the marker effect)
      final adjustedRect = Rect.fromLTRB(
        lineRect.left + horizontalPadding - 2,
        centerY - highlightHeight / 2 + verticalPadding,
        lineRect.right + horizontalPadding + 2,
        centerY + highlightHeight / 2 + verticalPadding,
      );
      _drawMarkerStroke(canvas, adjustedRect, i);
    }
  }

  void _drawMarkerStroke(Canvas canvas, Rect rect, int lineIndex) {
    // Create the marker path with organic edges
    final path = _createOrganicPath(rect, lineIndex);

    // Layer 1: Base color with gradient for ink density effect
    final baseGradient = LinearGradient(
      begin: Alignment.topCenter,
      end: Alignment.bottomCenter,
      colors: [
        color.withValues(alpha: opacity * 0.65),
        color.withValues(alpha: opacity),
        color.withValues(alpha: opacity * 0.75),
      ],
      stops: const [0.0, 0.5, 1.0],
    );

    final basePaint = Paint()
      ..shader = baseGradient.createShader(rect)
      ..style = PaintingStyle.fill;

    canvas.drawPath(path, basePaint);

    // Layer 2: Subtle edge darkening for marker edge effect
    final edgePaint = Paint()
      ..color = color.withValues(alpha: opacity * 0.25)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 0.3);

    canvas.drawPath(path, edgePaint);
  }

  /// Creates a path with slightly organic/wavy edges to simulate hand-drawn marker
  Path _createOrganicPath(Rect rect, int lineIndex) {
    final path = Path();

    // Seed for consistent randomness based on rect dimensions and line index
    final seed = ((rect.width * rect.height).toInt() + lineIndex * 1000) % 100000;
    final random = math.Random(seed);

    // Parameters for organic effect - subtle for a cleaner look
    const wobbleAmount = 0.8;
    const cornerRadius = 2.5;

    // Helper to add slight variation
    double wobble() => (random.nextDouble() - 0.5) * wobbleAmount;

    // Slight random rotation/skew for hand-drawn feel
    final skewOffset = (random.nextDouble() - 0.5) * 1.0;

    // Start from top-left with rounded corner
    path.moveTo(
      rect.left + cornerRadius + wobble(),
      rect.top + wobble() + skewOffset,
    );

    // Top edge - slight wave
    path.lineTo(
      rect.right - cornerRadius + wobble(),
      rect.top + wobble() - skewOffset,
    );

    // Top-right corner
    path.quadraticBezierTo(
      rect.right + wobble(),
      rect.top + wobble(),
      rect.right + wobble(),
      rect.top + cornerRadius + wobble(),
    );

    // Right edge
    path.lineTo(
      rect.right + wobble(),
      rect.bottom - cornerRadius + wobble(),
    );

    // Bottom-right corner
    path.quadraticBezierTo(
      rect.right + wobble(),
      rect.bottom + wobble(),
      rect.right - cornerRadius + wobble(),
      rect.bottom + wobble() - skewOffset,
    );

    // Bottom edge
    path.lineTo(
      rect.left + cornerRadius + wobble(),
      rect.bottom + wobble() + skewOffset,
    );

    // Bottom-left corner
    path.quadraticBezierTo(
      rect.left + wobble(),
      rect.bottom + wobble(),
      rect.left + wobble(),
      rect.bottom - cornerRadius + wobble(),
    );

    // Left edge
    path.lineTo(
      rect.left + wobble(),
      rect.top + cornerRadius + wobble(),
    );

    // Top-left corner (close the path)
    path.quadraticBezierTo(
      rect.left + wobble(),
      rect.top + wobble(),
      rect.left + cornerRadius + wobble(),
      rect.top + wobble() + skewOffset,
    );

    path.close();
    return path;
  }

  @override
  bool shouldRepaint(covariant MultiLineMarkerPainter oldDelegate) {
    return oldDelegate.color != color ||
        oldDelegate.opacity != opacity ||
        oldDelegate.lineRects != lineRects ||
        oldDelegate.horizontalPadding != horizontalPadding ||
        oldDelegate.verticalPadding != verticalPadding;
  }
}

/// An inline text span that renders with a marker highlight effect.
/// Use this within RichText or Text.rich for inline highlights.
class MarkerHighlightSpan extends WidgetSpan {
  MarkerHighlightSpan({
    required String text,
    required Color color,
    TextStyle? style,
    double opacity = 0.55,
  }) : super(
          alignment: PlaceholderAlignment.baseline,
          baseline: TextBaseline.alphabetic,
          child: MarkerHighlight(
            color: color,
            opacity: opacity,
            verticalPadding: 1.0,
            horizontalPadding: 3.0,
            child: Text(
              text,
              style: (style ?? const TextStyle()).copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        );
}