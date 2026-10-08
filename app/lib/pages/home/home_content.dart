import 'package:flutter/material.dart';

import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The Home page of the shell: the live capture row, Daily Recaps, then every conversation, loading
/// more as it scrolls. Home and the Conversations tab are one page since 2026-09-29; search,
/// folders, starred and places open from the header's search button.
class HomeContentPage extends StatefulWidget {
  const HomeContentPage({super.key, this.requestInitialLoad = true, this.loadRecaps});

  /// See [ConversationsPage.requestInitialLoad].
  final bool requestInitialLoad;

  /// Injectable for tests and the visual audit; defaults to the recaps endpoint.
  final RecentRecapsLoader? loadRecaps;

  @override
  State<HomeContentPage> createState() => HomeContentPageState();
}

class HomeContentPageState extends State<HomeContentPage> {
  final GlobalKey<State<ConversationsPage>> _listKey = GlobalKey<State<ConversationsPage>>();
  final _nativeKey = GlobalKey<IosNativeHomeState>();
  late final Future<bool> _nativeSupport = supportsNativePresentation();

  void scrollToTop() {
    // The classic list is mounted on its own, or as the native Home's fallback after a rejection.
    final list = _listKey.currentState;
    if (list != null) {
      (list as dynamic).scrollToTop();
      return;
    }
    _nativeKey.currentState?.scrollToTop();
  }

  @override
  Widget build(BuildContext context) {
    final classic = ConversationsPage(
      key: _listKey,
      requestInitialLoad: widget.requestInitialLoad,
      loadRecaps: widget.loadRecaps,
    );
    if (!nativePresentationEnabled) return classic;
    return FutureBuilder<bool>(
      future: _nativeSupport,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) return const Center(child: OmiSpinner());
        if (snapshot.hasError) return OmiErrorState(message: context.l10n.connectionErrorDesc);
        if (snapshot.data != true) return classic;
        return IosNativeHome(
          key: _nativeKey,
          requestInitialLoad: widget.requestInitialLoad,
          loadRecaps: widget.loadRecaps,
          fallback: classic,
        );
      },
    );
  }
}
