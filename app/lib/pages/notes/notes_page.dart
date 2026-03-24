import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/note.dart';
import 'package:omi/providers/notes_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'widgets/note_item.dart';
import 'widgets/note_edit_sheet.dart';

class NotesPage extends StatefulWidget {
  const NotesPage({super.key});

  @override
  State<NotesPage> createState() => NotesPageState();
}

class NotesPageState extends State<NotesPage> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  final TextEditingController _searchController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  OverlayEntry? _deleteNotificationOverlay;
  NoteType? _selectedFilter;

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    _removeDeleteNotification();
    super.dispose();
  }

  void _removeDeleteNotification() {
    _deleteNotificationOverlay?.remove();
    _deleteNotificationOverlay = null;
  }

  void showDeleteNotification(String noteTitle, Note note) {
    _removeDeleteNotification();

    final provider = Provider.of<NotesProvider>(context, listen: false);

    _deleteNotificationOverlay = OverlayEntry(
      builder: (_) => Positioned(
        bottom: 20,
        left: 0,
        right: 0,
        child: Center(
          child: Material(
            color: Colors.transparent,
            child: Container(
              width: MediaQuery.of(context).size.width * 0.9,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: Colors.black87,
                borderRadius: BorderRadius.circular(8),
                boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.2), blurRadius: 4, offset: const Offset(0, 2))],
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      'Note deleted',
                      style: const TextStyle(color: Colors.white, fontSize: 14),
                    ),
                  ),
                  TextButton(
                    onPressed: () async {
                      final success = await provider.restoreLastDeletedNote();
                      if (success) {
                        _removeDeleteNotification();
                      }
                    },
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      minimumSize: const Size(0, 36),
                    ),
                    child: Text(
                      'Undo',
                      style: const TextStyle(color: Colors.blue, fontWeight: FontWeight.w500),
                    ),
                  ),
                  IconButton(
                    onPressed: () {
                      _removeDeleteNotification();
                    },
                    icon: const Icon(Icons.close, color: Colors.white70, size: 20),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                    splashRadius: 20,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );

    Overlay.of(context).insert(_deleteNotificationOverlay!);

    Future.delayed(const Duration(seconds: 4), () {
      if (!mounted) return;
      _removeDeleteNotification();
    });
  }

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      MixpanelManager().notesPageOpened();
      final provider = Provider.of<NotesProvider>(context, listen: false);
      if (provider.notes.isEmpty) {
        provider.fetchNotes(showShimmer: true);
      }
    });
  }

  void _onScroll() {
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      final provider = Provider.of<NotesProvider>(context, listen: false);
      if (!provider.isFetching && provider.hasMore) {
        provider.loadMoreNotes();
      }
    }
  }

  void scrollToTop() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(0, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
    }
  }

  void _onSearchChanged(String query) {
    Provider.of<NotesProvider>(context, listen: false).setSearchQuery(query);
  }

  void _onFilterChanged(NoteType? type) {
    setState(() {
      _selectedFilter = type;
    });
    Provider.of<NotesProvider>(context, listen: false).setFilterType(type);
  }

  void _showEditSheet(Note? note) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => NoteEditSheet(
        note: note,
        onSave: (content, title, duration, transcription) async {
          final provider = Provider.of<NotesProvider>(context, listen: false);
          if (note != null) {
            await provider.updateNote(
              note.id,
              content: content,
              title: title,
              duration: duration,
              transcription: transcription,
            );
          } else {
            await provider.createNote(
              content: content,
              title: title,
              type: NoteType.voice,
              duration: duration,
              transcription: transcription,
            );
          }
        },
      ),
    );
  }

  void _deleteNote(Note note) {
    final provider = Provider.of<NotesProvider>(context, listen: false);
    provider.deleteNote(note.id);
    showDeleteNotification(note.displayTitle, note);
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Consumer<NotesProvider>(
      builder: (context, provider, _) {
        return PopScope(
          canPop: true,
          child: Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            body: Stack(
              children: [
                RefreshIndicator(
                  onRefresh: () async {
                    HapticFeedback.mediumImpact();
                    await provider.refresh();
                  },
                  color: Colors.deepPurpleAccent,
                  backgroundColor: Colors.white,
                  child: CustomScrollView(
                    controller: _scrollController,
                    physics: const AlwaysScrollableScrollPhysics(),
                    slivers: [
                      SliverToBoxAdapter(
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(16, 12, 16, 10),
                          child: Column(
                            children: [
                              // Search bar
                              Row(
                                children: [
                                  Expanded(
                                    child: SizedBox(
                                      height: 44,
                                      child: SearchBar(
                                        hintText: 'Search notes...',
                                        leading: const Padding(
                                          padding: EdgeInsets.only(left: 6.0),
                                          child: Icon(
                                            FontAwesomeIcons.magnifyingGlass,
                                            color: Colors.white70,
                                            size: 14,
                                          ),
                                        ),
                                        trailing: provider.searchQuery.isNotEmpty
                                            ? [
                                                IconButton(
                                                  icon: const Icon(Icons.clear, color: Colors.white70, size: 16),
                                                  onPressed: () {
                                                    _searchController.clear();
                                                    _onSearchChanged('');
                                                  },
                                                ),
                                              ]
                                            : null,
                                        backgroundColor: WidgetStateProperty.all(AppStyles.backgroundSecondary),
                                        elevation: WidgetStateProperty.all(0),
                                        padding: WidgetStateProperty.all(
                                          const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                                        ),
                                        hintStyle: WidgetStateProperty.all(
                                          TextStyle(color: AppStyles.textTertiary, fontSize: 14),
                                        ),
                                        textStyle: WidgetStateProperty.all(
                                          const TextStyle(color: AppStyles.textPrimary, fontSize: 14),
                                        ),
                                        onChanged: _onSearchChanged,
                                        controller: _searchController,
                                        shape: WidgetStateProperty.all(
                                          RoundedRectangleBorder(
                                            borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              // Filter chips
                              Row(
                                children: [
                                  _buildFilterChip(
                                    label: 'All',
                                    isSelected: _selectedFilter == null,
                                    onTap: () => _onFilterChanged(null),
                                  ),
                                  const SizedBox(width: 8),
                                  _buildFilterChip(
                                    label: 'Voice',
                                    isSelected: _selectedFilter == NoteType.voice,
                                    onTap: () => _onFilterChanged(NoteType.voice),
                                    icon: FontAwesomeIcons.microphone,
                                  ),
                                  const SizedBox(width: 8),
                                  _buildFilterChip(
                                    label: 'Text',
                                    isSelected: _selectedFilter == NoteType.text,
                                    onTap: () => _onFilterChanged(NoteType.text),
                                    icon: FontAwesomeIcons.pen,
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                      // Notes list
                      if (provider.isLoading && provider.notes.isEmpty)
                        SliverPadding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          sliver: SliverList(
                            delegate: SliverChildBuilderDelegate(
                              (context, index) => _buildShimmerItem(),
                              childCount: 5,
                            ),
                          ),
                        )
                      else if (provider.filteredNotes.isEmpty)
                        SliverFillRemaining(
                          hasScrollBody: false,
                          child: Center(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  FontAwesomeIcons.noteSticky,
                                  size: 64,
                                  color: Colors.white.withOpacity(0.3),
                                ),
                                const SizedBox(height: 16),
                                Text(
                                  'No notes yet',
                                  style: TextStyle(
                                    color: Colors.white.withOpacity(0.5),
                                    fontSize: 18,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  'Triple tap your device button to record',
                                  style: TextStyle(
                                    color: Colors.white.withOpacity(0.3),
                                    fontSize: 14,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        )
                      else
                        SliverPadding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          sliver: SliverList(
                            delegate: SliverChildBuilderDelegate(
                              (context, index) {
                                final note = provider.filteredNotes[index];
                                return Padding(
                                  padding: const EdgeInsets.only(bottom: 12),
                                  child: NoteItem(
                                    note: note,
                                    onTap: () => _showEditSheet(note),
                                    onDelete: () => _deleteNote(note),
                                  ),
                                );
                              },
                              childCount: provider.filteredNotes.length,
                            ),
                          ),
                        ),
                      // Bottom padding for nav bar
                      const SliverToBoxAdapter(
                        child: SizedBox(height: 120),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildFilterChip({
    required String label,
    required bool isSelected,
    required VoidCallback onTap,
    IconData? icon,
  }) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        onTap();
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? Colors.deepPurple : AppStyles.backgroundSecondary,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? Colors.deepPurpleAccent : Colors.transparent,
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[
              Icon(
                icon,
                size: 12,
                color: isSelected ? Colors.white : Colors.white70,
              ),
              const SizedBox(width: 6),
            ],
            Text(
              label,
              style: TextStyle(
                color: isSelected ? Colors.white : Colors.white70,
                fontSize: 13,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildShimmerItem() {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppStyles.backgroundSecondary,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  height: 14,
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
                const SizedBox(height: 8),
                Container(
                  height: 12,
                  width: 150,
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
