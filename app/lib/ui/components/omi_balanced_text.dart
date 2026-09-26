import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';

/// Short UI copy that wraps into even lines instead of leaving one word alone on the last line
/// (CSS `text-wrap: balance`): "Start with this phone, or connect / a device to listen all day."
/// rather than "… to listen all / day.".
///
/// A card whose copy changes with state keeps its height when [reserveFor] names the other copy it
/// can show ("Start with this phone, or connect a device…" and "Pendant · Ready"): the text holds
/// the height of the tallest of them at this width and text size, so nothing below it moves.
/// [minLines] holds at least that many lines. For titles, card subtitles, empty states and sheet
/// descriptions — not for user content.
class OmiBalancedText extends StatelessWidget {
  const OmiBalancedText(
    this.data, {
    super.key,
    this.style,
    this.textAlign,
    this.maxLines,
    this.minLines = 1,
    this.reserveFor = const [],
    this.overflow,
  });

  final String data;
  final TextStyle? style;
  final TextAlign? textAlign;
  final int? maxLines;
  final int minLines;
  final List<String> reserveFor;
  final TextOverflow? overflow;

  @override
  Widget build(BuildContext context) {
    final centered = textAlign == TextAlign.center;
    Widget text = _BalancedWidth(
      alignment: centered ? Alignment.topCenter : AlignmentDirectional.topStart,
      balance: !data.contains('\n'),
      maxLines: maxLines,
      child: Text(data, style: style, textAlign: textAlign, maxLines: maxLines, overflow: overflow),
    );
    final reserved = [
      if (minLines > 1) '\n' * (minLines - 1),
      for (final other in reserveFor)
        if (other != data) other,
    ];
    if (reserved.isEmpty) return text;
    // The other copy is laid out unseen (no paint, no semantics) so the box is as tall as the
    // tallest of them.
    return Stack(
      alignment: centered ? Alignment.topCenter : AlignmentDirectional.topStart,
      children: [
        for (final other in reserved)
          Visibility(
            visible: false,
            maintainSize: true,
            maintainAnimation: true,
            maintainState: true,
            child: Text(other, style: style, textAlign: textAlign, maxLines: maxLines, overflow: overflow),
          ),
        text,
      ],
    );
  }
}

/// Lays its text child out at the narrowest width that keeps the lines it takes at the full width.
class _BalancedWidth extends SingleChildRenderObjectWidget {
  const _BalancedWidth({required this.alignment, required this.balance, required this.maxLines, required super.child});

  final AlignmentGeometry alignment;
  final bool balance;
  final int? maxLines;

  @override
  RenderObject createRenderObject(BuildContext context) =>
      _RenderBalancedWidth(alignment, balance, maxLines, Directionality.of(context));

  @override
  void updateRenderObject(BuildContext context, _RenderBalancedWidth renderObject) {
    renderObject
      ..alignment = alignment
      ..balance = balance
      ..maxLines = maxLines
      ..textDirection = Directionality.of(context);
  }
}

class _RenderBalancedWidth extends RenderShiftedBox {
  _RenderBalancedWidth(this._alignment, this._balance, this._maxLines, this._textDirection) : super(null);

  AlignmentGeometry _alignment;
  set alignment(AlignmentGeometry value) {
    if (value == _alignment) return;
    _alignment = value;
    markNeedsLayout();
  }

  bool _balance;
  set balance(bool value) {
    if (value == _balance) return;
    _balance = value;
    markNeedsLayout();
  }

  int? _maxLines;
  set maxLines(int? value) {
    if (value == _maxLines) return;
    _maxLines = value;
    markNeedsLayout();
  }

  TextDirection _textDirection;
  set textDirection(TextDirection value) {
    if (value == _textDirection) return;
    _textDirection = value;
    markNeedsLayout();
  }

  /// The width to lay the text out at: the narrowest, at most [maxWidth], that keeps the lines it
  /// takes at [maxWidth], so the lines come out even. Text that fits one line, breaks lines itself,
  /// or is cut short keeps the full width. Measured with a painter on the paragraph's own settings,
  /// so dry layout and layout agree.
  double _balancedWidth(RenderBox child, double maxWidth) {
    if (!_balance || !maxWidth.isFinite || maxWidth <= 0 || child is! RenderParagraph) return maxWidth;
    var placeholder = false;
    child.text.visitChildren((span) {
      if (span is PlaceholderSpan) placeholder = true;
      return !placeholder;
    });
    if (placeholder) return maxWidth;
    final painter = TextPainter(
      text: child.text,
      textAlign: child.textAlign,
      textDirection: child.textDirection,
      textScaler: child.textScaler,
      maxLines: child.maxLines,
      locale: child.locale,
      strutStyle: child.strutStyle,
      textWidthBasis: child.textWidthBasis,
      textHeightBehavior: child.textHeightBehavior,
    );
    try {
      int linesAt(double width) {
        painter.layout(maxWidth: width);
        return painter.didExceedMaxLines ? -1 : painter.computeLineMetrics().length;
      }

      final lines = linesAt(maxWidth);
      if (lines < 2) return maxWidth;
      var fits = maxWidth;
      var tooNarrow = 0.0;
      while (fits - tooNarrow > 1) {
        final width = (fits + tooNarrow) / 2;
        if (linesAt(width) != lines) {
          tooNarrow = width;
        } else {
          fits = width;
        }
      }
      return fits.ceilToDouble().clamp(0.0, maxWidth);
    } finally {
      painter.dispose();
    }
  }

  @override
  Size computeDryLayout(BoxConstraints constraints) {
    final child = this.child;
    if (child == null) return constraints.smallest;
    final width = _balancedWidth(child, constraints.maxWidth);
    return constraints.constrain(child.getDryLayout(constraints.copyWith(minWidth: 0, maxWidth: width)));
  }

  @override
  void performLayout() {
    final child = this.child;
    if (child == null) {
      size = constraints.smallest;
      return;
    }
    final width = _balancedWidth(child, constraints.maxWidth);
    child.layout(constraints.copyWith(minWidth: 0, maxWidth: width), parentUsesSize: true);
    size = constraints.constrain(child.size);
    final parentData = child.parentData! as BoxParentData;
    parentData.offset = _alignment.resolve(_textDirection).alongOffset(size - child.size as Offset);
  }
}
