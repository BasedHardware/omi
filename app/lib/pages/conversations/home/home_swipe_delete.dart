import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A Home row that swipes open to a round red delete button (#20038). Every deletable Home row uses it,
/// so a conversation and a recording saved on this phone delete the same way.
///
/// A short swipe leaves the row open with the button showing; tapping it asks [confirm], whose menu
/// pops from the button. A swipe past [_askAt] of the row's width opens the row and asks straight
/// away, as the old swipe-to-delete did. Tapping the open card, swiping it back or scrolling the list
/// closes it. Once [confirm] says yes, the card slides away and [onDeleted] runs.
class HomeSwipeDelete extends StatefulWidget {
  const HomeSwipeDelete(
      {super.key, required this.enabled, required this.confirm, required this.onDeleted, required this.child});

  final bool enabled;

  /// Asks to delete; [anchor] is the delete button's rect on screen.
  final Future<bool> Function(Rect anchor) confirm;
  final VoidCallback onDeleted;
  final Widget child;

  @override
  State<HomeSwipeDelete> createState() => HomeSwipeDeleteState();
}

class HomeSwipeDeleteState extends State<HomeSwipeDelete> with SingleTickerProviderStateMixin {
  static const double _button = 44;
  static const double _inset = 16;

  /// How far the card rests open: the button and the air on either side of it.
  static const double _open = _button + 2 * _inset;

  /// Past this share of the row's width, letting go asks straight away.
  static const double _askAt = 0.4;

  /// How far the card is pulled aside, in logical pixels.
  AnimationController? _offsetController;
  AnimationController get _offset => _offsetController ??= AnimationController.unbounded(vsync: this);
  final GlobalKey _buttonKey = GlobalKey();
  ValueListenable<bool>? _scrolling;
  double _width = 0;
  bool _asking = false;

  bool get _rtl => Directionality.of(context) == TextDirection.rtl;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final scrolling = Scrollable.maybeOf(context)?.position.isScrollingNotifier;
    if (scrolling != _scrolling) {
      _scrolling?.removeListener(_onScroll);
      _scrolling = scrolling?..addListener(_onScroll);
    }
  }

  @override
  void didUpdateWidget(HomeSwipeDelete oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!widget.enabled && _offset.value != 0) _settle(0);
  }

  @override
  void dispose() {
    _scrolling?.removeListener(_onScroll);
    // Never create the controller here: a row that was never swiped has no ticker left to give it.
    _offsetController?.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrolling!.value && !_asking && _offset.value > 0) _settle(0);
  }

  Future<void> _settle(double to) =>
      _offset.animateTo(to, duration: OmiMotion.of(context).standard, curve: Curves.easeOutCubic);

  void _onDragUpdate(DragUpdateDetails details) {
    if (_asking) return;
    final delta = _rtl ? details.primaryDelta! : -details.primaryDelta!;
    _offset.value = (_offset.value + delta).clamp(0.0, _width);
  }

  void _onDragEnd(DragEndDetails details) {
    if (_asking) return;
    final velocity = _rtl ? details.primaryVelocity! : -details.primaryVelocity!;
    if (_offset.value >= _width * _askAt) {
      _settle(_open);
      _ask();
      return;
    }
    final open = velocity > 300 || (velocity > -300 && _offset.value > _open / 2);
    _settle(open ? _open : 0);
  }

  Future<void> _ask() async {
    final box = _buttonKey.currentContext?.findRenderObject() as RenderBox?;
    if (_asking || box == null) return;
    _asking = true;
    final confirmed = await widget.confirm(box.localToGlobal(Offset.zero) & box.size);
    if (!mounted) return;
    _asking = false;
    if (!confirmed) {
      _settle(0);
      return;
    }
    await _offset.animateTo(_width, duration: OmiMotion.of(context).quick, curve: Curves.easeIn);
    if (!mounted) return;
    widget.onDeleted();
    // The list drops the row in the next frame; if it is still here after that, show it closed.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _offset.value = 0;
    });
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        _width = constraints.maxWidth;
        return GestureDetector(
          onHorizontalDragUpdate: widget.enabled ? _onDragUpdate : null,
          onHorizontalDragEnd: widget.enabled ? _onDragEnd : null,
          child: Stack(
            children: [
              if (widget.enabled)
                Positioned.fill(
                  child: Align(
                    alignment: AlignmentDirectional.centerEnd,
                    child: Padding(
                      padding: const EdgeInsetsDirectional.only(end: _inset),
                      child: AnimatedBuilder(
                        animation: _offset,
                        builder: (context, child) {
                          final t = Curves.easeOut.transform((_offset.value / _open).clamp(0.0, 1.0));
                          return Opacity(
                            opacity: t,
                            child: Transform.scale(scale: 0.6 + 0.4 * t, child: child),
                          );
                        },
                        child: Semantics(
                          button: true,
                          label: context.l10n.delete,
                          child: GestureDetector(
                            key: _buttonKey,
                            behavior: HitTestBehavior.opaque,
                            onTap: _ask,
                            child: Container(
                              key: const ValueKey('conversation_swipe_delete'),
                              width: _button,
                              height: _button,
                              // Without it the glyph sits in the circle's top-left corner.
                              alignment: Alignment.center,
                              decoration: BoxDecoration(color: OmiColors.danger, shape: BoxShape.circle),
                              child: const FaIcon(FontAwesomeIcons.trashCan, size: 17, color: Colors.white),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              AnimatedBuilder(
                animation: _offset,
                builder: (context, child) => Transform.translate(
                  offset: Offset(_rtl ? _offset.value : -_offset.value, 0),
                  child: Stack(
                    children: [
                      child!,
                      // While open, a tap on the card closes it instead of opening the conversation.
                      if (_offset.value > 0)
                        Positioned.fill(
                          child: GestureDetector(behavior: HitTestBehavior.opaque, onTap: () => _settle(0)),
                        ),
                    ],
                  ),
                ),
                child: widget.child,
              ),
            ],
          ),
        );
      },
    );
  }
}
