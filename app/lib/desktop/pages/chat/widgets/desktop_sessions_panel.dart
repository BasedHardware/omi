import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/molecules/omi_section_header.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/http/api/messages.dart';

class DesktopSessionsPanel extends StatefulWidget {
  final VoidCallback onClose;

  const DesktopSessionsPanel({super.key, required this.onClose});

  @override
  State<DesktopSessionsPanel> createState() => _DesktopSessionsPanelState();
}

class _DesktopSessionsPanelState extends State<DesktopSessionsPanel> {
  final TextEditingController _searchCtrl = TextEditingController();
  final ValueNotifier<String> _query = ValueNotifier('');

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        context.read<MessageProvider>().loadSessions();
      }
    });
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    _query.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.95),
        border: Border(left: BorderSide(color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3), width: 1)),
      ),
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 12, 8),
              child: Row(
                children: [
                  const OmiSectionHeader(icon: FontAwesomeIcons.clockRotateLeft, title: 'Chat History'),
                  const Spacer(),
                  IconButton(
                    tooltip: 'New chat',
                    icon: const Icon(Icons.add_circle_outline, color: ResponsiveHelper.textSecondary),
                    onPressed: () async {
                      final appId = context.read<AppProvider>().selectedChatAppId;
                      await context.read<MessageProvider>().startNewChat(appId: appId);
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: const Text('New chat started'),
                            backgroundColor: ResponsiveHelper.backgroundTertiary,
                            behavior: SnackBarBehavior.floating,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                            duration: const Duration(seconds: 2),
                          ),
                        );
                      }
                    },
                  ),
                  IconButton(
                    tooltip: 'Close',
                    icon: const Icon(FontAwesomeIcons.xmark, size: 16, color: ResponsiveHelper.textSecondary),
                    onPressed: widget.onClose,
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: ResponsiveHelper.backgroundQuaternary.withValues(alpha: 0.3), width: 1),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.search, color: ResponsiveHelper.textSecondary, size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: TextField(
                        controller: _searchCtrl,
                        style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14),
                        decoration: const InputDecoration(
                          hintText: 'Search chats',
                          hintStyle: TextStyle(color: ResponsiveHelper.textTertiary),
                          border: InputBorder.none,
                          isDense: true,
                        ),
                        onChanged: (v) => _query.value = v.trim().toLowerCase(),
                      ),
                    ),
                    const SizedBox(width: 8),
                    if (_searchCtrl.text.isNotEmpty)
                      GestureDetector(
                        onTap: () {
                          _searchCtrl.clear();
                          _query.value = '';
                          setState(() {});
                        },
                        child: const Icon(FontAwesomeIcons.xmark, size: 14, color: ResponsiveHelper.textSecondary),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: Consumer<MessageProvider>(builder: (context, mp, _) {
                return ValueListenableBuilder<String>(
                  valueListenable: _query,
                  builder: (context, q, __) {
                    final sessions = mp.sessions;
                    final List<Map<String, dynamic>> filtered = q.isEmpty
                        ? sessions
                        : sessions.where((s) {
                            final t = ((s['title'] as String?) ?? '').toLowerCase();
                            return t.contains(q);
                          }).toList();
                    if (filtered.isEmpty) {
                      return const Center(
                        child: Text('No sessions', style: TextStyle(color: ResponsiveHelper.textSecondary)),
                      );
                    }
                    return ListView.builder(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                      itemCount: filtered.length,
                      itemBuilder: (context, i) {
                        final s = filtered[i];
                        final id = s['id'] as String? ?? '';
                        final title = (s['title'] as String?)?.trim();
                        final display = (title != null && title.isNotEmpty) ? title : 'Chat';
                        final isCurrent = context.read<MessageProvider>().currentChatSessionId == id;
                        return Container(
                          margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color:
                                isCurrent ? ResponsiveHelper.backgroundTertiary.withOpacity(0.8) : Colors.transparent,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: ListTile(
                            dense: true,
                            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
                            title: Text(
                              display,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14),
                            ),
                            trailing: IconButton(
                              tooltip: 'Delete',
                              icon: const Icon(Icons.delete_outline, color: ResponsiveHelper.textSecondary, size: 18),
                              onPressed: () async {
                                try {
                                  final mp = context.read<MessageProvider>();
                                  await deleteChatSessionServer(id);
                                  if (mp.currentChatSessionId == id) {
                                    await mp.startNewChat(appId: context.read<AppProvider>().selectedChatAppId);
                                  }
                                  await mp.loadSessions();
                                  if (mounted) {
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      SnackBar(
                                        content: const Text('Chat deleted'),
                                        backgroundColor: ResponsiveHelper.backgroundTertiary,
                                        behavior: SnackBarBehavior.floating,
                                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                        duration: const Duration(seconds: 2),
                                      ),
                                    );
                                  }
                                } catch (_) {}
                              },
                            ),
                            onTap: () async {
                              widget.onClose();
                              final p = context.read<MessageProvider>();
                              await p.switchToSession(id);
                            },
                          ),
                        );
                      },
                    );
                  },
                );
              }),
            ),
          ],
        ),
      ),
    );
  }
}
