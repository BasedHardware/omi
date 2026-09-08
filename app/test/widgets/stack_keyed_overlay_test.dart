import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Reproduces the structural bug behind the keyboard-flicker on
/// `conversation_detail/page.dart`: a body `Stack` whose two conditional
/// children (a floating bottom bar that hides when the keyboard rises, and
/// a search overlay that holds the search `TextField`) are both `Positioned`
/// widgets with no `Key`.
///
/// When the bottom bar's `if` flips false, Flutter's element diff
/// (`canUpdate == same runtimeType && same key`) walks the new children
/// `[GD, SearchOverlay]` against the old `[GD, BottomBar, SearchOverlay]`
/// and matches the surviving Positioned to the *first* slot it sees — the
/// one previously held by BottomBar. The old SearchOverlay element at
/// slot 2 is deactivated. That tears down the entire subtree below it,
/// including the `TextField`'s `State`. In the real app this drops the
/// `TextInputConnection` mid-frame and the soft keyboard collapses.
///
/// These tests assert that fact with a `_DisposeCounter` inside the
/// "overlay" subtree — a buggy structure recreates its `State` when the
/// sibling drops out; a keyed structure does not.

class _DisposeCounter extends StatefulWidget {
  const _DisposeCounter({required this.counter});
  final _LifecycleLog counter;

  @override
  State<_DisposeCounter> createState() => _DisposeCounterState();
}

class _LifecycleLog {
  int initCount = 0;
  int disposeCount = 0;
}

class _DisposeCounterState extends State<_DisposeCounter> {
  @override
  void initState() {
    super.initState();
    widget.counter.initCount += 1;
  }

  @override
  void dispose() {
    widget.counter.disposeCount += 1;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return const SizedBox(width: 10, height: 10);
  }
}

/// Builds the same shape as the production body Stack:
/// `[GestureDetector, if(showBar) Positioned(bar), if(showOverlay) Positioned(overlay)]`.
/// `useKeys` toggles whether the two conditional children carry a stable
/// `ValueKey` — i.e. the fix.
Widget _buildHarness({
  required bool showBar,
  required bool showOverlay,
  required _LifecycleLog overlayCounter,
  required bool useKeys,
}) {
  return MaterialApp(
    home: Scaffold(
      body: Stack(
        children: [
          GestureDetector(onTap: () {}, child: const SizedBox.expand()),
          if (showBar)
            Positioned(
              key: useKeys ? const ValueKey('bar') : null,
              bottom: 32,
              left: 0,
              right: 0,
              child: const SizedBox(height: 40),
            ),
          if (showOverlay)
            Positioned(
              key: useKeys ? const ValueKey('overlay') : null,
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              // The Stack > Positioned > Container > SafeArea > _DisposeCounter
              // shape mirrors the real search overlay's wrapper chain so the
              // diff has the same depth as production.
              child: Stack(
                children: [
                  Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    child: Container(
                      padding: const EdgeInsets.all(16),
                      child: SafeArea(
                        child: _DisposeCounter(counter: overlayCounter),
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    ),
  );
}

void main() {
  testWidgets('without keys: removing the bottom-bar sibling tears down the overlay subtree', (tester) async {
    final overlay = _LifecycleLog();

    await tester.pumpWidget(_buildHarness(
      showBar: true,
      showOverlay: true,
      overlayCounter: overlay,
      useKeys: false,
    ));
    expect(overlay.initCount, 1, reason: 'overlay child should mount once');
    expect(overlay.disposeCount, 0);

    // Simulates the keyboard rising: bottom bar's `if` flips false. Overlay is
    // still requested; production sees the same children-list collapse.
    await tester.pumpWidget(_buildHarness(
      showBar: false,
      showOverlay: true,
      overlayCounter: overlay,
      useKeys: false,
    ));

    // The bug: Flutter reuses the bar's Positioned element for the overlay's
    // new slot, deactivating the old overlay element. The overlay subtree is
    // disposed and rebuilt — which in production hides the IME.
    expect(overlay.disposeCount, 1, reason: 'buggy diff disposes the overlay subtree');
    expect(overlay.initCount, 2, reason: 'and immediately remounts it (new State)');
  });

  testWidgets('with keys: removing the bottom-bar sibling preserves the overlay subtree', (tester) async {
    final overlay = _LifecycleLog();

    await tester.pumpWidget(_buildHarness(
      showBar: true,
      showOverlay: true,
      overlayCounter: overlay,
      useKeys: true,
    ));
    expect(overlay.initCount, 1);
    expect(overlay.disposeCount, 0);

    await tester.pumpWidget(_buildHarness(
      showBar: false,
      showOverlay: true,
      overlayCounter: overlay,
      useKeys: true,
    ));

    // With ValueKeys, the surviving overlay element is matched by key, not by
    // slot+type, so its subtree is preserved. The TextField in production
    // keeps its TextInputConnection → keyboard stays open.
    expect(overlay.disposeCount, 0, reason: 'keyed diff keeps the overlay element');
    expect(overlay.initCount, 1, reason: 'no remount');
  });
}
