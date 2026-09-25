import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The chat's app picker, opened from the chat header.
///
/// Top to bottom: pick who you chat with (Omi or an enabled chat app), "Enable Apps" to add more,
/// and — at the bottom, away from the everyday actions — Clear Chat. Each app that is not the
/// current one has a labelled "Disable {app}" control; it disables the app everywhere, with Undo.
class ChatAppsDrawer extends StatelessWidget {
  const ChatAppsDrawer({
    super.key,
    required this.onSelectApp,
    required this.onEnableApps,
    required this.onDisableApp,
    required this.onClearChat,
  });

  /// The id of the chosen app, or `'no_selected'` for Omi.
  final ValueChanged<String> onSelectApp;
  final VoidCallback onEnableApps;
  final ValueChanged<App> onDisableApp;
  final VoidCallback onClearChat;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Drawer(
      backgroundColor: OmiColors.surface1,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.horizontal(left: Radius.circular(OmiRadius.lg)),
      ),
      child: SafeArea(
        child: Consumer2<MessageProvider, AppProvider>(
          builder: (context, messageProvider, appProvider, child) {
            final chatApps = messageProvider.chatApps;
            final selectedAppId = appProvider.selectedChatAppId;
            final isOmiSelected = chatApps.firstWhereOrNull((a) => a.id == selectedAppId) == null;

            void choose(String id) {
              Navigator.of(context).pop();
              onSelectApp(id);
            }

            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsetsDirectional.fromSTEB(OmiSpacing.lg, OmiSpacing.xs, OmiSpacing.xxs, 0),
                  child: Row(
                    children: [
                      Expanded(
                        child: Semantics(header: true, child: Text(l10n.chatAppsTitle, style: OmiType.title3)),
                      ),
                      const OmiCloseButton(color: OmiColors.textSecondary),
                    ],
                  ),
                ),
                const Divider(color: OmiColors.border, height: 1),
                Padding(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.lg, OmiSpacing.xs),
                  child: Text(
                    l10n.selectApp,
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                  ),
                ),
                Expanded(
                  child: ListView(
                    padding: EdgeInsets.zero,
                    children: [
                      _AppRow(
                        avatar: const ChatOmiAvatar(),
                        name: l10n.omiAppName,
                        isSelected: isOmiSelected,
                        onTap: () => choose('no_selected'),
                      ),
                      for (final app in chatApps)
                        _AppRow(
                          avatar: ChatAppAvatar(app: app),
                          name: app.getName(),
                          isSelected: selectedAppId == app.id,
                          onTap: () => choose(app.id),
                          onDisable: selectedAppId != app.id ? () => onDisableApp(app) : null,
                        ),
                      if (chatApps.isEmpty)
                        Padding(
                          padding: const EdgeInsets.all(OmiSpacing.lg),
                          child: Text(
                            l10n.noChatAppsEnabled,
                            style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      ListTile(
                        leading: const Padding(
                          padding: EdgeInsets.only(left: 2),
                          child: FaIcon(FontAwesomeIcons.circlePlus, color: OmiColors.textPrimary, size: 20),
                        ),
                        title: Text(l10n.enableApps, style: OmiType.callout),
                        trailing: const Icon(Icons.chevron_right, color: OmiColors.textTertiary),
                        onTap: () {
                          Navigator.of(context).pop();
                          onEnableApps();
                        },
                      ),
                    ],
                  ),
                ),
                const Divider(color: OmiColors.border, height: 1),
                ListTile(
                  leading: const Padding(
                    padding: EdgeInsets.only(left: 2),
                    child: FaIcon(FontAwesomeIcons.solidTrashCan, color: OmiColors.danger, size: 20),
                  ),
                  title: Text(l10n.clearChat, style: OmiType.callout.copyWith(color: OmiColors.danger)),
                  onTap: () {
                    Navigator.of(context).pop();
                    onClearChat();
                  },
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _AppRow extends StatelessWidget {
  const _AppRow({
    required this.avatar,
    required this.name,
    required this.isSelected,
    required this.onTap,
    this.onDisable,
  });

  final Widget avatar;
  final String name;
  final bool isSelected;
  final VoidCallback onTap;

  /// Null for Omi and for the app you are chatting with (switch away first).
  final VoidCallback? onDisable;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: avatar,
      title: Text(name, style: OmiType.callout, overflow: TextOverflow.ellipsis),
      trailing: isSelected
          ? const ExcludeSemantics(
              child: FaIcon(FontAwesomeIcons.solidCircleCheck, color: OmiColors.textPrimary, size: 18))
          : onDisable == null
              ? null
              : OmiIconButton(
                  icon: const FaIcon(FontAwesomeIcons.circleMinus, size: 18),
                  label: context.l10n.disableAppNamed(name),
                  color: OmiColors.textTertiary,
                  onPressed: onDisable,
                ),
      selected: isSelected,
      selectedTileColor: OmiColors.surface2,
      onTap: onTap,
    );
  }
}

/// A chat app's round avatar (24 pt).
class ChatAppAvatar extends StatelessWidget {
  const ChatAppAvatar({super.key, required this.app});

  final App app;

  @override
  Widget build(BuildContext context) {
    return CachedNetworkImage(
      imageUrl: app.getImageUrl(),
      imageBuilder: (context, imageProvider) =>
          CircleAvatar(backgroundColor: Colors.white, radius: 12, backgroundImage: imageProvider),
      errorWidget: (context, url, error) => const CircleAvatar(
        backgroundColor: OmiColors.surface3,
        radius: 12,
        child: Icon(Icons.apps, size: 14, color: OmiColors.textSecondary),
      ),
      placeholder: (context, url) => const CircleAvatar(backgroundColor: OmiColors.surface3, radius: 12),
    );
  }
}

/// Omi's own avatar (24 pt), matching [ChatAppAvatar].
class ChatOmiAvatar extends StatelessWidget {
  const ChatOmiAvatar({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        image: DecorationImage(image: AssetImage(Assets.images.background.path), fit: BoxFit.cover),
        borderRadius: OmiRadius.lgAll,
      ),
      height: 24,
      width: 24,
      alignment: Alignment.center,
      child: Image.asset(Assets.images.herologo.path, height: 16, width: 16),
    );
  }
}
