import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/chat/chat_screen.dart';
import 'package:nooto_v2/chat/chat_storage.dart';
import 'package:nooto_v2/home/home_screen.dart';
import 'package:nooto_v2/home/home_storage.dart';
import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/providers/auth_provider.dart';
import 'package:nooto_v2/shell/bottom_nav_bar.dart';
import 'package:nooto_v2/shell/stubs/coming_soon_stub.dart';
import 'package:nooto_v2/theme/app_theme.dart';

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
    return Scaffold(
      backgroundColor: AppColors.backgroundPrimary,
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        flexibleSpace: ClipRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
            child: Container(
              color: AppColors.backgroundPrimary.withValues(alpha: 0.55),
            ),
          ),
        ),
        elevation: 0,
        // Home leads with cards; other tabs use the tab label.
        // The wordmark on Home is quiet brand presence — replaces the
        // institutional "Início" without going back to a centered title.
        titleSpacing: 16,
        title: _index == 0
            ? Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Nooto',
                  style: brandSerif(
                    fontSize: 16,
                    color: AppColors.textTertiary,
                  ),
                ),
              )
            : Text(
                tabs[_index].label,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textPrimary,
                ),
              ),
        actions: [
          PopupMenuButton<String>(
            tooltip: 'More',
            icon: const Icon(Icons.more_vert, color: AppColors.textTertiary, size: 20),
            color: AppColors.backgroundSecondary,
            onSelected: (v) async {
              if (v == 'signout') {
                await context.read<AuthChangeProvider>().signOut();
              } else if (v == 'reset') {
                await _confirmReset();
              }
            },
            itemBuilder: (_) => [
              const PopupMenuItem(value: 'signout', child: Text('Sign out', style: TextStyle(color: AppColors.textPrimary))),
              if (kDebugMode)
                const PopupMenuItem(value: 'reset', child: Text('Reset onboarding', style: TextStyle(color: AppColors.textPrimary))),
            ],
          ),
        ],
      ),
      body: IndexedStack(
        index: _index,
        children: [
          for (var i = 0; i < tabs.length; i++)
            if (i == 0)
              HomeScreen(
                onSwitchToTab: (idx) =>
                    _switchTab(idx, focusChat: idx == 1),
              )
            else if (i == 1)
              // Rebuild ChatScreen when autoFocus changes so the post-frame
              // focus request fires once per arrival from the Home composer.
              ChatScreen(
                key: ValueKey('chat-$_autoFocusChat'),
                autoFocus: _autoFocusChat && _index == 1,
              )
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

  Future<void> _confirmReset() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.backgroundSecondary,
        title: const Text('Reset onboarding?', style: TextStyle(color: AppColors.textPrimary)),
        content: const Text(
          'This wipes your saved chat state and starts over.',
          style: TextStyle(color: AppColors.textTertiary),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Reset', style: TextStyle(color: AppColors.errorColor)),
          ),
        ],
      ),
    );
    if (!mounted || ok != true) return;
    await HomeBoxes.clearAll();
    await ChatBoxes.clearAll();
    if (!mounted) return;
    await context.read<OnboardingChatProvider>().reset();
  }
}

class _Tab {
  final String label;
  final IconData icon;
  const _Tab({required this.label, required this.icon});
}
