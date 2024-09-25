import 'package:flutter/material.dart';

class ExpansionTileCard extends StatefulWidget {
  const ExpansionTileCard({
    super.key,
    this.leading,
    required this.title,
    this.subtitle,
    this.onExpansionChanged,
    this.children = const <Widget>[],
    this.trailing,
    this.borderRadius = const BorderRadius.all(Radius.circular(8.0)),
    this.elevation = 2.0,
    this.initialElevation = 0.0,
    this.initiallyExpanded = false,
    this.initialPadding = EdgeInsets.zero,
    this.finalPadding = const EdgeInsets.only(bottom: 6.0),
    this.contentPadding,
    this.baseColor,
    this.expandedColor,
    this.expandedTextColor,
    this.duration = const Duration(milliseconds: 200),
    this.elevationCurve = Curves.easeOut,
    this.heightFactorCurve = Curves.easeIn,
    this.turnsCurve = Curves.easeIn,
    this.colorCurve = Curves.easeIn,
    this.paddingCurve = Curves.easeIn,
    this.isThreeLine = false,
    this.shadowColor = const Color(0xffaaaaaa),
    this.animateTrailing = false,
    required this.expandedTextStyle,
    required this.collapsedTextStyle,
  });

  final bool isThreeLine;
  final Widget? leading;
  final String title;
  final Widget? subtitle;
  final ValueChanged<bool>? onExpansionChanged;
  final List<Widget> children;
  final Widget? trailing;
  final bool animateTrailing;
  final BorderRadiusGeometry borderRadius;
  final double elevation;
  final double initialElevation;
  final Color shadowColor;
  final bool initiallyExpanded;
  final EdgeInsetsGeometry initialPadding;
  final EdgeInsetsGeometry finalPadding;
  final EdgeInsetsGeometry? contentPadding;
  final Color? baseColor;

  final TextStyle expandedTextStyle;

  final TextStyle collapsedTextStyle;
  final Color? expandedColor;
  final Color? expandedTextColor;
  final Duration duration;
  final Curve elevationCurve;
  final Curve heightFactorCurve;
  final Curve turnsCurve;
  final Curve colorCurve;
  final Curve paddingCurve;

  @override
  ExpansionTileCardState createState() => ExpansionTileCardState();
}

class ExpansionTileCardState extends State<ExpansionTileCard> with SingleTickerProviderStateMixin {
  static final Animatable<double> _halfTween = Tween<double>(begin: 0.0, end: 0.5);

  final ColorTween _headerColorTween = ColorTween();
  final ColorTween _iconColorTween = ColorTween();
  final ColorTween _materialColorTween = ColorTween();
  late EdgeInsetsTween _edgeInsetsTween;
  late Animatable<double> _elevationTween;
  late Animatable<double> _heightFactorTween;
  late Animatable<double> _turnsTween;
  late Animatable<double> _colorTween;
  late Animatable<double> _paddingTween;

  late AnimationController _controller;
  late Animation<double> _iconTurns;
  late Animation<double> _heightFactor;
  late Animation<double> _elevation;
  late Animation<Color?> _headerColor;
  late Animation<Color?> _iconColor;
  late Animation<Color?> _materialColor;
  late Animation<EdgeInsets> _padding;

  bool _isExpanded = false;

  @override
  void initState() {
    super.initState();
    _edgeInsetsTween = EdgeInsetsTween(
      begin: widget.initialPadding as EdgeInsets?,
      end: widget.finalPadding as EdgeInsets?,
    );
    _elevationTween = CurveTween(curve: widget.elevationCurve);
    _heightFactorTween = CurveTween(curve: widget.heightFactorCurve);
    _colorTween = CurveTween(curve: widget.colorCurve);
    _turnsTween = CurveTween(curve: widget.turnsCurve);
    _paddingTween = CurveTween(curve: widget.paddingCurve);

    _controller = AnimationController(duration: widget.duration, vsync: this);
    _heightFactor = _controller.drive(_heightFactorTween);
    _iconTurns = _controller.drive(_halfTween.chain(_turnsTween));
    _headerColor = _controller.drive(_headerColorTween.chain(_colorTween));
    _materialColor = _controller.drive(_materialColorTween.chain(_colorTween));
    _iconColor = _controller.drive(_iconColorTween.chain(_colorTween));
    _elevation =
        _controller.drive(Tween<double>(begin: widget.initialElevation, end: widget.elevation).chain(_elevationTween));
    _padding = _controller.drive(_edgeInsetsTween.chain(_paddingTween));
    _isExpanded = PageStorage.of(context).readState(context) as bool? ?? widget.initiallyExpanded;
    if (_isExpanded) _controller.value = 1.0;
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  // Credit: Simon Lightfoot - https://stackoverflow.com/a/48935106/955974
  void _setExpansion(bool shouldBeExpanded) {
    if (shouldBeExpanded != _isExpanded) {
      setState(() {
        _isExpanded = shouldBeExpanded;
        if (_isExpanded) {
          _controller.forward();
        } else {
          _controller.reverse().then<void>((void value) {
            if (!mounted) return;
            setState(() {});
          });
        }
        PageStorage.of(context).writeState(context, _isExpanded);
      });
      if (widget.onExpansionChanged != null) {
        widget.onExpansionChanged!(_isExpanded);
      }
    }
  }

  void expand() {
    _setExpansion(true);
  }

  void collapse() {
    _setExpansion(false);
  }

  void toggleExpansion() {
    _setExpansion(!_isExpanded);
  }

  Widget _buildChildren(BuildContext context, Widget? child) {
    return Padding(
      padding: _padding.value,
      child: Material(
        type: MaterialType.card,
        color: _materialColor.value,
        borderRadius: widget.borderRadius,
        elevation: _elevation.value,
        shadowColor: widget.shadowColor,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            InkWell(
              customBorder: RoundedRectangleBorder(borderRadius: widget.borderRadius),
              onTap: toggleExpansion,
              child: ListTileTheme.merge(
                iconColor: _iconColor.value,
                textColor: _headerColor.value,
                child: Padding(
                  padding: const EdgeInsets.all(2.0),
                  child: ListTile(
                    isThreeLine: widget.isThreeLine,
                    contentPadding: widget.contentPadding,
                    leading: widget.leading,
                    title: Text(
                      widget.title,
                      style: _isExpanded ? widget.expandedTextStyle : widget.collapsedTextStyle,
                    ),
                    subtitle: widget.subtitle,
                    trailing: RotationTransition(
                      turns: widget.trailing == null || widget.animateTrailing
                          ? _iconTurns
                          : const AlwaysStoppedAnimation(0),
                      child: widget.trailing ??
                          Icon(
                            Icons.expand_more,
                            color: _isExpanded ? widget.expandedTextStyle.color : widget.collapsedTextStyle.color,
                          ),
                    ),
                  ),
                ),
              ),
            ),
            ClipRect(
              child: Align(
                heightFactor: _heightFactor.value,
                child: child,
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void didChangeDependencies() {
    final ThemeData theme = Theme.of(context);
    _headerColorTween
      ..begin = theme.textTheme.titleMedium!.color
      ..end = widget.expandedTextColor ?? theme.colorScheme.secondary;
    _iconColorTween
      ..begin = theme.unselectedWidgetColor
      ..end = widget.expandedTextColor ?? theme.colorScheme.secondary;
    _materialColorTween
      ..begin = widget.baseColor ?? theme.canvasColor
      ..end = widget.expandedColor ?? theme.cardColor;
    super.didChangeDependencies();
  }

  @override
  Widget build(BuildContext context) {
    final bool closed = !_isExpanded && _controller.isDismissed;
    return AnimatedBuilder(
      animation: _controller.view,
      builder: _buildChildren,
      child: closed ? null : Column(children: widget.children),
    );
  }
}
