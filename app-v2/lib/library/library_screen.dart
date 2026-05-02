import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/library/conversation_detail_screen.dart';
import 'package:nooto_v2/library/conversations_provider.dart';
import 'package:nooto_v2/library/views/conversations_view.dart';
import 'package:nooto_v2/library/views/memories_view.dart';
import 'package:nooto_v2/library/widgets/library_section_tab_bar.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Library shell. Mirrors desktop-v2/src/components/library/LibraryPage:
/// a glass AppBar header with a pill sub-tab strip for Meetings / Memories.
/// The sub-tab state lives in [ShellScreen] so the pill bar can render
/// inside the AppBar's `bottom:` slot, unifying the chrome.
class LibraryScreen extends StatelessWidget {
  const LibraryScreen({super.key, required this.subTab});

  final LibrarySubTab subTab;

  @override
  Widget build(BuildContext context) {
    return subTab == LibrarySubTab.meetings
        ? const ConversationsView()
        : MemoriesView(
            onViewConversation: (cid) => _openConversation(context, cid),
          );
  }

  /// Loads the conversation by id (cached by [ConversationsProvider] in the
  /// common case) and pushes the detail screen. Falls back to a snack if not
  /// in cache yet — v0.1 will fetch by id directly.
  Future<void> _openConversation(BuildContext context, String id) async {
    final provider = context.read<ConversationsProvider>();
    if (!provider.hasFetched) {
      await provider.load();
    }
    final item = provider.byId(id);
    if (!context.mounted) return;
    if (item == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text("Couldn't find that conversation. Try refreshing Meetings."),
          backgroundColor: AppColors.backgroundSecondary,
        ),
      );
      return;
    }
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ConversationDetailScreen(item: item),
      ),
    );
  }
}

/// Library sub-tab identifier. Lives at module scope so [ShellScreen] can
/// hoist the active tab and render the pill bar in its AppBar.
enum LibrarySubTab { meetings, memories }

/// Tab specs (icon + label) used by the shell to build the pill bar. Kept
/// alongside the enum so a future tab insertion only touches one place.
const List<LibrarySectionTab<LibrarySubTab>> librarySubTabSpecs = [
  LibrarySectionTab(
    id: LibrarySubTab.meetings,
    label: 'Meetings',
    icon: Icons.graphic_eq_rounded,
  ),
  LibrarySectionTab(
    id: LibrarySubTab.memories,
    label: 'Memories',
    icon: Icons.psychology_alt_rounded,
  ),
];
