import 'dart:async';
import 'dart:ui' as ui;

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The two-bubbles glyph (FontAwesome `comments`) that FontAwesome surfaces still use for Ask Omi.
const FaIconData kAskOmiGlyph = FontAwesomeIcons.comments;

/// Height of the floating tab capsule (v2 `controls.tabBarHeight`).
const double kBottomNavRowHeight = OmiSize.tabBar;

/// Height of the tab capsule; kept as the bar's own height above its offset from the screen edge.
const double kBottomNavBarHeight = kBottomNavRowHeight;

/// Gap between the top of the tab capsule and anything that floats above it (the Home record
/// button). Derived from the capsule's geometry so the two cannot drift.
const double kBottomNavChatBarGap = OmiSpacing.xs;

/// Air between the top of the capsule and the last row of content scrolled above it.
const double _kContentAir = OmiSpacing.sm;

/// The bottom inset the bar reserves for system chrome. Anything positioned against the bar must
/// add this to stay in step with it.
///
/// viewPadding, not padding: the home Scaffold sets resizeToAvoidBottomInset: false, and
/// padding.bottom collapses to zero while a keyboard is open, which would drop the bar back under
/// the system bar.
double bottomNavBarReservedInset(BuildContext context) => MediaQuery.viewPaddingOf(context).bottom;

/// Distance from the bottom of the screen to the bottom of the capsule. The v2 bar floats half-way
/// into the home-indicator area: 25 pt above the edge with a 34 pt inset, 8 pt with none
/// (`layout.tabBarBottom = 25 + (safeBottom - 34) / 2`). It never sits inside a taller inset such as
/// Android's three-button bar: its bottom stays at or above half of it.
double bottomNavBarBottomOffset(BuildContext context) {
  final inset = bottomNavBarReservedInset(context);
  final floating = OmiSpacing.xs + inset / 2;
  // A three-button navigation bar is opaque and tappable; never draw under it.
  return inset > 34 ? inset + OmiSpacing.xs : floating;
}

/// Distance from the bottom of the screen to the top of the capsule plus a little air. Content that
/// scrolls or floats behind the bar in the home shell clears this rather than a literal.
double bottomNavBarClearance(BuildContext context) =>
    bottomNavBarBottomOffset(context) + kBottomNavRowHeight + _kContentAir;

/// Height of the slot that floats above the capsule on Home (the record button).
const double kHomeChatBarHeight = 62;

/// Offset from the bottom of the screen to the bottom edge of what floats above the capsule.
double bottomNavChatBarOffset(BuildContext context) =>
    bottomNavBarBottomOffset(context) + kBottomNavRowHeight + kBottomNavChatBarGap;

/// Distance from the bottom of the screen that home-tab content must clear to stay out from under
/// the floating record button, with a little air above it.
double homeChatBarClearance(BuildContext context) =>
    bottomNavChatBarOffset(context) + kHomeChatBarHeight + OmiSpacing.lg;

class _Tab {
  const _Tab(this.analyticsName, this.glyph, this.selectedGlyph);

  final String analyticsName;
  final String glyph;
  final String selectedGlyph;
}

// Rev 3 tabs in the Liquid Dock's icon set: outline at rest, filled when selected.
const List<_Tab> _tabs = [
  _Tab('Home', 'assets/icons/tab-today.svg', 'assets/icons/tab-today-fill.svg'),
  _Tab('Conversations', 'assets/icons/tab-conversations.svg', 'assets/icons/tab-conversations-fill.svg'),
  _Tab('Tasks', 'assets/icons/tab-todo.svg', 'assets/icons/tab-todo-fill.svg'),
  _Tab('Apps', 'assets/icons/grid.svg', 'assets/icons/grid-fill.svg'),
];

/// Dock geometry, expanded and folded (Liquid Dock).
class _DockMetrics {
  const _DockMetrics({
    required this.height,
    required this.padding,
    required this.tabHeight,
    required this.minTabWidth,
    required this.tabPadding,
    required this.icon,
    required this.ask,
    required this.ring,
    required this.lensInset,
  });

  final double height;
  final double padding;
  final double tabHeight;
  final double minTabWidth;
  final double tabPadding;
  final double icon;
  final double ask;
  final double ring;
  final double lensInset;

  static const expanded = _DockMetrics(
    height: kBottomNavRowHeight,
    padding: 6,
    tabHeight: 54,
    minTabWidth: 64,
    tabPadding: 8,
    icon: 26,
    ask: 54,
    ring: 28,
    lensInset: 5,
  );

  /// Scrolled down: labels fold away, every tab stays one tap away.
  static const compact = _DockMetrics(
    height: 52,
    padding: 5,
    tabHeight: 44,
    minTabWidth: 50,
    tabPadding: 4,
    icon: 23,
    ask: 44,
    ring: 24,
    lensInset: 4,
  );
}

const double _kGap = 2;

/// The narrowest the open Ask field lays out at (mark, field, send), however narrow the dock is.
const double _kAskFieldMinWidth = 200;

/// How long the Omi mark is held to open Memories instead of Ask.
const Duration kAskHoldDuration = Duration(seconds: 2);
const Duration _kFold = Duration(milliseconds: 550);
const Duration _kGlide = Duration(milliseconds: 500);

/// The home shell's dock (Liquid Dock): one glass capsule holding the four tabs and Ask. A lens
/// slides under the selected tab (with a small jelly squash as it lands) and the tab's icon fills
/// and lifts. Scrolling down folds it to icons ([compact]); Ask opens the dock into a field — what
/// is typed there goes to Chat ([onAskSubmit]) — and tapping the mark again opens Chat itself.
class BottomNavBar extends StatefulWidget {
  const BottomNavBar({
    super.key,
    required this.onTabTap,
    this.onTabWarmup,
    this.onAskTap,
    this.onAskSubmit,
    this.onAskHold,
    this.compact,
  });

  /// Called when a tab is chosen; `isRepeat` when it was already selected (scroll to top).
  final void Function(int index, bool isRepeat) onTabTap;

  /// Called on touch-down so the destination can start building before the tap completes.
  final void Function(int index)? onTabWarmup;

  /// Opens Chat. Null hides Ask.
  final VoidCallback? onAskTap;

  /// A question typed into the open dock. Null makes Ask open Chat directly.
  final ValueChanged<String>? onAskSubmit;

  /// Holding the Omi mark for [kAskHoldDuration] (a firm haptic when it fires): Memories. A hidden
  /// shortcut, also offered to screen readers as a named action.
  final VoidCallback? onAskHold;

  /// Scroll-driven fold (labels hidden). Null keeps the dock expanded.
  final ValueListenable<bool>? compact;

  @override
  State<BottomNavBar> createState() => _BottomNavBarState();
}

class _BottomNavBarState extends State<BottomNavBar> {
  bool _asking = false;
  final TextEditingController _question = TextEditingController();
  final FocusNode _questionFocus = FocusNode();

  /// While asking, the dock and its scrim rise above the whole screen — the header, To do's New
  /// Task, any floating bar — so only the question is lit. The dock keeps its state on the way up
  /// and back ([_dockKey]), so it still grows into the field.
  final OverlayPortalController _askLayer = OverlayPortalController();
  final GlobalKey _dockKey = GlobalKey(debugLabel: 'bottom_nav_dock');

  @override
  void dispose() {
    _question.dispose();
    _questionFocus.dispose();
    super.dispose();
  }

  void _openAsk() {
    if (widget.onAskSubmit == null) {
      widget.onAskTap?.call();
      return;
    }
    OmiHaptics.selection();
    _askLayer.show();
    setState(() => _asking = true);
    Future.delayed(const Duration(milliseconds: 380), () {
      if (mounted && _asking) _questionFocus.requestFocus();
    });
  }

  void _closeAsk() {
    _questionFocus.unfocus();
    if (!mounted) return;
    _askLayer.hide();
    setState(() => _asking = false);
  }

  void _submit() {
    final text = _question.text.trim();
    if (text.isEmpty) return;
    _question.clear();
    _closeAsk();
    OmiHaptics.light();
    widget.onAskSubmit?.call(text);
  }

  /// Tab widths for [m]: at least the minimum, wide enough for the label when it shows.
  List<double> _widths(BuildContext context, List<String> labels, _DockMetrics m, bool compact) {
    return [
      for (final label in labels)
        compact
            ? m.minTabWidth
            : () {
                final painter = TextPainter(
                  text: TextSpan(text: label, style: OmiType.tabLabel),
                  maxLines: 1,
                  textDirection: TextDirection.ltr,
                  textScaler: MediaQuery.textScalerOf(context).clamp(maxScaleFactor: 1.2),
                )..layout();
                final width = painter.width + m.tabPadding * 2;
                return width.clamp(m.minTabWidth, 104.0);
              }(),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final dock = KeyedSubtree(key: _dockKey, child: _buildDock(context));
    return OverlayPortal(
      controller: _askLayer,
      overlayChildBuilder: (_) => dock,
      child: _askLayer.isShowing ? const SizedBox.shrink() : dock,
    );
  }

  Widget _buildDock(BuildContext context) {
    // Keep the provider-dependent subtree narrow when HomePage's broad Consumer rebuilds for
    // unrelated focus or loading changes.
    return Selector<HomeProvider, int>(
      selector: (_, home) => home.selectedIndex,
      builder: (context, selectedIndex, _) {
        final labels = [context.l10n.today, context.l10n.conversations, context.l10n.toDo, context.l10n.apps];
        final compactListenable = widget.compact ?? const _AlwaysFalse();
        return ValueListenableBuilder<bool>(
          valueListenable: compactListenable,
          builder: (context, compact, _) {
            final folded = compact && !_asking;
            final m = folded ? _DockMetrics.compact : _DockMetrics.expanded;
            final screen = MediaQuery.sizeOf(context).width;
            final askSlot = widget.onAskTap == null ? 0.0 : m.ask + _kGap;
            // Never wider than the screen: long labels (a language, large text) share what is left.
            final room = screen - OmiSize.screenMargin * 2 - m.padding * 2 - askSlot - _kGap * (_tabs.length - 1);
            var widths = _widths(context, labels, m, folded);
            final wanted = widths.fold<double>(0, (a, b) => a + b);
            if (wanted > room && room > 0) widths = [for (final w in widths) w * room / wanted];
            final reduce = MediaQuery.disableAnimationsOf(context);
            final fold = reduce ? Duration.zero : _kFold;
            final keyboard = MediaQuery.viewInsetsOf(context).bottom;
            final askWidth = _asking ? 0.0 : askSlot;
            final tabsWidth = _asking ? 0.0 : widths.fold<double>(0, (a, b) => a + b) + _kGap * (_tabs.length - 1);
            final dockWidth =
                _asking ? (screen - OmiSize.screenMargin * 2).clamp(0.0, 370.0) : m.padding * 2 + tabsWidth + askWidth;
            var lensLeft = m.padding;
            for (var i = 0; i < selectedIndex.clamp(0, _tabs.length - 1); i++) {
              lensLeft += widths[i] + _kGap;
            }
            final bottom = _asking && keyboard > 0 ? keyboard + OmiSpacing.sm : bottomNavBarBottomOffset(context);
            return Stack(
              children: [
                if (_asking)
                  Positioned.fill(
                    child: GestureDetector(
                      key: const Key('bottom_nav_ask_scrim'),
                      onTap: _closeAsk,
                      child: const _AskScrim(),
                    ),
                  ),
                Align(
                  alignment: Alignment.bottomCenter,
                  child: AnimatedPadding(
                    duration: fold,
                    curve: OmiMotion.springCurve,
                    padding: EdgeInsets.only(bottom: bottom),
                    child: AnimatedContainer(
                      // Ask appearing or leaving is a different dock, not a resize to animate.
                      key: ValueKey(widget.onAskTap != null),
                      duration: fold,
                      curve: OmiMotion.springCurve,
                      width: dockWidth,
                      height: m.height,
                      child: OmiGlass(
                        borderRadius: OmiRadius.tabBarAll,
                        child: Stack(
                          clipBehavior: Clip.hardEdge,
                          children: [
                            // The lens: slides under the selected tab, squashes a little as it lands.
                            AnimatedPositioned(
                              duration: reduce ? Duration.zero : _kGlide,
                              curve: OmiMotion.springCurve,
                              left: lensLeft,
                              width: widths[selectedIndex.clamp(0, _tabs.length - 1)],
                              top: m.lensInset,
                              bottom: m.lensInset,
                              child: AnimatedOpacity(
                                opacity: _asking ? 0 : 1,
                                duration: const Duration(milliseconds: 300),
                                child: OmiDockLens(key: ValueKey(selectedIndex), animate: !reduce),
                              ),
                            ),
                            Positioned.fill(
                              child: Padding(
                                padding: EdgeInsets.symmetric(horizontal: m.padding),
                                child: Row(
                                  children: [
                                    for (var i = 0; i < _tabs.length; i++) ...[
                                      if (i > 0) const SizedBox(width: _kGap),
                                      AnimatedContainer(
                                        duration: fold,
                                        curve: OmiMotion.springCurve,
                                        width: _asking ? 0 : widths[i],
                                        height: m.tabHeight,
                                        child: ClipRect(
                                          child: AnimatedOpacity(
                                            duration: const Duration(milliseconds: 250),
                                            opacity: _asking ? 0 : 1,
                                            child: _buildTab(
                                                context, selectedIndex, i, _tabs[i], labels[i], m, folded, widths[i]),
                                          ),
                                        ),
                                      ),
                                    ],
                                    if (widget.onAskTap != null) ...[
                                      if (!_asking) const SizedBox(width: _kGap),
                                      Expanded(child: _buildAsk(context, m)),
                                    ],
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            );
          },
        );
      },
    );
  }

  Widget _buildTab(
    BuildContext context,
    int selectedIndex,
    int index,
    _Tab tab,
    String label,
    _DockMetrics m,
    bool folded,
    double width,
  ) {
    final selected = selectedIndex == index;
    final color = selected ? OmiColors.textPrimary : OmiColors.dockTabIdle;
    final reduce = MediaQuery.disableAnimationsOf(context);
    void activate() {
      if (_asking) return;
      // Switch the visible page before crossing the platform channel for haptics or analytics.
      // Both can be delayed when the device is busy, but neither should delay visual
      // acknowledgement of the tap.
      widget.onTabTap(index, context.read<HomeProvider>().selectedIndex == index);
      primaryFocus?.unfocus();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        OmiHaptics.selection();
        PlatformManager.instance.analytics.bottomNavigationTabClicked(tab.analyticsName);
      });
    }

    return Semantics(
      button: true,
      selected: selected,
      label: label,
      onTap: activate,
      excludeSemantics: true,
      child: GestureDetector(
        key: Key('bottom_nav_tab_$index'),
        behavior: HitTestBehavior.opaque,
        onTapDown: (_) => widget.onTabWarmup?.call(index),
        onTap: activate,
        child: OverflowBox(
          maxWidth: width,
          minWidth: width,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              // The selected icon fills and lifts a point (0.5 s spring).
              AnimatedSlide(
                duration: reduce ? Duration.zero : _kGlide,
                curve: OmiMotion.springCurve,
                offset: selected ? Offset(0, -1 / m.icon) : Offset.zero,
                child: AnimatedScale(
                  duration: reduce ? Duration.zero : _kGlide,
                  curve: OmiMotion.springCurve,
                  scale: selected ? 1.06 : 1,
                  child: AnimatedContainer(
                    duration: _kFold,
                    curve: OmiMotion.springCurve,
                    width: m.icon,
                    height: m.icon,
                    child: OmiGlyph(selected ? tab.selectedGlyph : tab.glyph, size: m.icon, color: color),
                  ),
                ),
              ),
              // Labels fold away when the dock is compact.
              AnimatedSize(
                duration: reduce ? Duration.zero : const Duration(milliseconds: 400),
                curve: OmiMotion.springCurve,
                child: folded
                    ? const SizedBox(width: 0, height: 0)
                    : Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: SizedBox(
                          width: (width - m.tabPadding).clamp(0.0, double.infinity),
                          child: FittedBox(
                            fit: BoxFit.scaleDown,
                            child: AnimatedDefaultTextStyle(
                              duration: OmiMotion.of(context).quick,
                              style: OmiType.tabLabel.copyWith(color: color),
                              child: Text(label, maxLines: 1, softWrap: false),
                            ),
                          ),
                        ),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Ask: the Omi ring; while asking, the dock's field ("Ask Omi anything") and a send button.
  Widget _buildAsk(BuildContext context, _DockMetrics m) {
    final l10n = context.l10n;
    final ring = OmiRingLogo(
      size: m.ring,
      mode: OmiRingMode.orbit,
      loops: omiLoopsEnabled(context) ? null : 1,
    );
    if (!_asking) {
      final hold = widget.onAskHold;
      return Semantics(
        button: true,
        label: l10n.askOmi,
        onTap: _openAsk,
        customSemanticsActions: hold == null ? null : {CustomSemanticsAction(label: l10n.memories): hold},
        excludeSemantics: true,
        child: _AskMark(
          key: const Key('bottom_nav_ask'),
          size: m.ask,
          onTap: _openAsk,
          onHold: hold,
          child: ring,
        ),
      );
    }
    // The field is laid out at full width from the first frame and clipped while the dock grows
    // around it, so nothing squeezes or overflows mid-animation.
    return ClipRect(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final width = constraints.maxWidth < _kAskFieldMinWidth ? _kAskFieldMinWidth : constraints.maxWidth;
          return OverflowBox(
            alignment: Alignment.centerLeft,
            minWidth: width,
            maxWidth: width,
            child: _askField(context, ring),
          );
        },
      ),
    );
  }

  Widget _askField(BuildContext context, Widget ring) {
    final l10n = context.l10n;
    return Row(
      children: [
        // The mark opens Chat itself (history, voice).
        Semantics(
          button: true,
          label: l10n.askOmi,
          excludeSemantics: true,
          onTap: () {
            _closeAsk();
            widget.onAskTap?.call();
          },
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () {
              _closeAsk();
              widget.onAskTap?.call();
            },
            child: SizedBox(width: 44, height: 44, child: Center(child: ring)),
          ),
        ),
        const SizedBox(width: OmiSpacing.xs),
        Expanded(
          child: TextField(
            key: const Key('bottom_nav_ask_field'),
            controller: _question,
            focusNode: _questionFocus,
            style: OmiType.body,
            cursorColor: OmiColors.textPrimary,
            textInputAction: TextInputAction.send,
            onSubmitted: (_) => _submit(),
            decoration: InputDecoration(
              isCollapsed: true,
              border: InputBorder.none,
              hintText: l10n.askAnything,
              hintStyle: OmiType.body.copyWith(color: OmiColors.textTertiary),
            ),
          ),
        ),
        const SizedBox(width: OmiSpacing.xs),
        Semantics(
          button: true,
          label: l10n.send,
          excludeSemantics: true,
          onTap: _submit,
          child: GestureDetector(
            key: const Key('bottom_nav_ask_send'),
            behavior: HitTestBehavior.opaque,
            onTap: _submit,
            child: SizedBox.square(
              dimension: OmiSize.minTap,
              child: Center(
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
                  child: Icon(Icons.arrow_upward_rounded, size: 20, color: OmiColors.onAccent),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// Behind the open Ask field: everything else blurs and dims in a quarter second, so the question
/// is the one lit thing on screen.
class _AskScrim extends StatelessWidget {
  const _AskScrim();

  @override
  Widget build(BuildContext context) {
    final reduce = MediaQuery.disableAnimationsOf(context);
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: reduce ? 1 : 0, end: 1),
      duration: const Duration(milliseconds: 240),
      curve: Curves.easeOut,
      builder: (context, t, _) => ClipRect(
        child: BackdropFilter(
          filter: ui.ImageFilter.blur(sigmaX: 14 * t, sigmaY: 14 * t),
          child: ColoredBox(color: OmiColors.scrim.withValues(alpha: OmiColors.scrim.a * t)),
        ),
      ),
    );
  }
}

/// The dock's Omi mark: a tap asks; held for [kAskHoldDuration] it runs [onHold] with a firm
/// haptic, and letting go then does nothing more. Read from raw touches rather than the gesture
/// arena so nothing around the dock can claim the hold, and a thumb may drift a little while it
/// waits. The mark swells while held so the reader can tell something is coming.
class _AskMark extends StatefulWidget {
  const _AskMark({super.key, required this.size, required this.onTap, this.onHold, required this.child});

  final double size;
  final VoidCallback onTap;
  final VoidCallback? onHold;
  final Widget child;

  @override
  State<_AskMark> createState() => _AskMarkState();
}

class _AskMarkState extends State<_AskMark> with SingleTickerProviderStateMixin {
  /// How far a held thumb may wander before the touch counts as neither a tap nor a hold.
  static const double _slop = kTouchSlop * 1.5;

  late final AnimationController _swell = AnimationController(vsync: this, duration: kAskHoldDuration);
  Timer? _timer;
  int? _pointer;
  Offset? _start;
  bool _held = false;

  @override
  void dispose() {
    _timer?.cancel();
    _swell.dispose();
    super.dispose();
  }

  void _down(PointerDownEvent event) {
    if (_pointer != null) return;
    _pointer = event.pointer;
    _start = event.position;
    _held = false;
    final hold = widget.onHold;
    if (hold == null) return;
    if (!MediaQuery.disableAnimationsOf(context)) _swell.forward(from: 0);
    _timer = Timer(kAskHoldDuration, () {
      _held = true;
      _swell.reverse();
      OmiHaptics.heavy();
      hold();
    });
  }

  void _move(PointerMoveEvent event) {
    final start = _start;
    if (event.pointer != _pointer || start == null) return;
    if ((event.position - start).distance > _slop) _end();
  }

  void _up(PointerUpEvent event) {
    if (event.pointer != _pointer) return;
    final tapped = !_held && _start != null;
    _end();
    if (tapped) widget.onTap();
  }

  void _cancel(PointerCancelEvent event) {
    if (event.pointer == _pointer) _end();
  }

  void _end() {
    _timer?.cancel();
    _timer = null;
    _pointer = null;
    _start = null;
    if (_swell.value > 0) _swell.reverse();
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      behavior: HitTestBehavior.opaque,
      onPointerDown: _down,
      onPointerMove: _move,
      onPointerUp: _up,
      onPointerCancel: _cancel,
      child: SizedBox(
        width: widget.size,
        height: widget.size,
        child: Center(
          child: ScaleTransition(
            scale: Tween<double>(begin: 1, end: 1.3).animate(CurvedAnimation(parent: _swell, curve: Curves.easeIn)),
            child: widget.child,
          ),
        ),
      ),
    );
  }
}

class _AlwaysFalse extends ValueListenable<bool> {
  const _AlwaysFalse();

  @override
  bool get value => false;

  @override
  void addListener(VoidCallback listener) {}

  @override
  void removeListener(VoidCallback listener) {}
}
