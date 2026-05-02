import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:nooto_v2/apps/apps_screen.dart';
import 'package:nooto_v2/chat/chat_screen.dart';
import 'package:nooto_v2/chat/widgets/chat_sessions_drawer.dart';
import 'package:nooto_v2/home/home_screen.dart';
import 'package:nooto_v2/library/library_screen.dart';
import 'package:nooto_v2/library/widgets/library_section_tab_bar.dart';
import 'package:nooto_v2/plan/plan_screen.dart';
import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/shell/app_bar_kebab_menu.dart';
import 'package:nooto_v2/shell/bottom_nav_bar.dart';
import 'package:nooto_v2/shell/stubs/coming_soon_stub.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// iOS HIG navigation bar height — Material defaults to 56pt which leaves
/// dead space below a single-line title; 44pt is the platform standard.
const double shellToolbarHeight = 44.0;

class ShellScreen extends StatefulWidget {
  const ShellScreen({super.key});

  @override
  State<ShellScreen> createState() => _ShellScreenState();
}

class _ShellScreenState extends State<ShellScreen> {
  int _index = 0;
  // When the Home composer pill navigates here, we focus the chat input on
  // arrival so the keyboard pops in the same gesture. Reset after consuming.
  bool _autoFocusChat = false;
  // Library has internal sub-tabs (Meetings / Memories). State lives here so
  // the AppBar can render the pill row in its `bottom:` slot — that keeps
  // chrome unified and avoids the "two floating headers with a gap" look.
  LibrarySubTab _librarySubTab = LibrarySubTab.meetings;

  void _switchTab(int idx, {bool focusChat = false}) {
    setState(() {
      _index = idx;
      _autoFocusChat = focusChat;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final tabs = <_Tab>[
      _Tab(label: l.shellTabHome, icon: FontAwesomeIcons.house),
      _Tab(label: l.shellTabChat, icon: FontAwesomeIcons.message),
      _Tab(label: l.shellTabLibrary, icon: FontAwesomeIcons.bookOpen),
      _Tab(label: l.shellTabPlan, icon: FontAwesomeIcons.calendarCheck),
      _Tab(label: l.shellTabApps, icon: FontAwesomeIcons.tableCellsLarge),
    ];
    final isHome = _index == 0;
    final isChat = _index == 1;
    final isLibrary = _index == 2;
    return Scaffold(
      backgroundColor: AppColors.backgroundPrimary,
      extendBodyBehindAppBar: !isHome,
      drawer: isChat ? const ChatSessionsDrawer() : null,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        toolbarHeight: shellToolbarHeight,
        // Drawer hamburger only on Chat tab; default leading is null on the
        // others so the AppBar doesn't render an unsupported menu icon.
        automaticallyImplyLeading: isChat,
        flexibleSpace: ClipRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
            child: Container(color: AppColors.backgroundPrimary.withValues(alpha: 0.55)),
          ),
        ),
        elevation: 0,
        titleSpacing: 16,
        title: isHome
            ? null
            : Text(
                tabs[_index].label,
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
              ),
        actions: const [AppBarKebabMenu()],
        bottom: isLibrary
            ? PreferredSize(
                preferredSize: const Size.fromHeight(LibrarySectionTabBar.height),
                child: LibrarySectionTabBar<LibrarySubTab>(
                  tabs: librarySubTabSpecs,
                  active: _librarySubTab,
                  onChanged: (id) => setState(() => _librarySubTab = id),
                ),
              )
            : null,
      ),
      body: IndexedStack(
        index: _index,
        children: [
          for (var i = 0; i < tabs.length; i++)
            if (i == 0)
              HomeScreen(onSwitchToTab: (idx) => _switchTab(idx, focusChat: idx == 1))
            else if (i == 1)
              ChatScreen(key: ValueKey('chat-$_autoFocusChat'), autoFocus: _autoFocusChat && _index == 1)
            else if (i == 2)
              LibraryScreen(subTab: _librarySubTab)
            else if (i == 3)
              const PlanScreen()
            else if (i == 4)
              const AppsScreen()
            else
              ComingSoonStub(tabLabel: tabs[i].label, icon: tabs[i].icon),
        ],
      ),
      bottomNavigationBar: ShellTabBar(
        selectedIndex: _index,
        onTap: (i) => _switchTab(i),
        labels: tabs.map((t) => t.label).toList(),
      ),
    );
  }
}

class _Tab {
  final String label;
  final IconData icon;
  const _Tab({required this.label, required this.icon});
}
