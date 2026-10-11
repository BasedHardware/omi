import 'package:flutter/material.dart';

import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/home/widgets/home_daily_recaps.dart';

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

  void scrollToTop() {
    final list = _listKey.currentState;
    if (list != null) (list as dynamic).scrollToTop();
  }

  @override
  Widget build(BuildContext context) {
    return ConversationsPage(
      key: _listKey,
      requestInitialLoad: widget.requestInitialLoad,
      loadRecaps: widget.loadRecaps,
    );
  }
}
