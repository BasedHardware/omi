import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/chat/chat_storage.dart';
import 'package:nooto_v2/home/home_storage.dart';
import 'package:nooto_v2/onboarding/onboarding_chat_provider.dart';
import 'package:nooto_v2/providers/auth_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Sign-out + (debug) reset menu. Lives in the trailing slot of whichever
/// AppBar/SliverAppBar is on screen — extracted so Home's SliverAppBar.large
/// and ShellScreen's compact AppBar can share it.
class AppBarKebabMenu extends StatefulWidget {
  const AppBarKebabMenu({super.key});

  @override
  State<AppBarKebabMenu> createState() => _AppBarKebabMenuState();
}

class _AppBarKebabMenuState extends State<AppBarKebabMenu> {
  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<String>(
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
        const PopupMenuItem(
          value: 'signout',
          child: Text('Sign out', style: TextStyle(color: AppColors.textPrimary)),
        ),
        if (kDebugMode)
          const PopupMenuItem(
            value: 'reset',
            child: Text('Reset onboarding', style: TextStyle(color: AppColors.textPrimary)),
          ),
      ],
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
