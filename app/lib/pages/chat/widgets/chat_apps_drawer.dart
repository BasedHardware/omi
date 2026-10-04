import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
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
        borderRadius: BorderRadius.horizontal(
          left: Radius.circular(OmiRadius.lg),
        ),
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

            final classic = Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsetsDirectional.fromSTEB(
                    OmiSpacing.lg,
                    OmiSpacing.xs,
                    OmiSpacing.xxs,
                    0,
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Semantics(
                          header: true,
                          child: Text(
                            l10n.chatAppsTitle,
                            style: OmiType.title3,
                          ),
                        ),
                      ),
                      OmiCloseButton(color: OmiColors.textSecondary),
                    ],
                  ),
                ),
                Divider(color: OmiColors.border, height: 1),
                Expanded(
                  // The rows say what they are: no "Select App" label above them, and no empty-state
                  // sentence that explains the Enable Apps row below it.
                  child: ListView(
                    padding: const EdgeInsets.only(top: OmiSpacing.xs),
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
                      ListTile(
                        leading: Padding(
                          padding: const EdgeInsets.only(left: 2),
                          child: FaIcon(
                            FontAwesomeIcons.circlePlus,
                            color: OmiColors.textPrimary,
                            size: 20,
                          ),
                        ),
                        title: Text(l10n.enableApps, style: OmiType.callout),
                        trailing: Icon(
                          Icons.chevron_right,
                          color: OmiColors.textTertiary,
                        ),
                        onTap: () {
                          Navigator.of(context).pop();
                          onEnableApps();
                        },
                      ),
                    ],
                  ),
                ),
                Divider(color: OmiColors.border, height: 1),
                ListTile(
                  leading: Padding(
                    padding: const EdgeInsets.only(left: 2),
                    child: FaIcon(
                      FontAwesomeIcons.solidTrashCan,
                      color: OmiColors.danger,
                      size: 20,
                    ),
                  ),
                  title: Text(
                    l10n.clearChat,
                    style: OmiType.callout.copyWith(color: OmiColors.danger),
                  ),
                  onTap: () {
                    Navigator.of(context).pop();
                    onClearChat();
                  },
                ),
              ],
            );
            return IosNativeSurface(
              title: l10n.chatAppsTitle,
              fallback: classic,
              loading: messageProvider.isLoadingChatApps,
              toolbar: [
                NativeRow(
                  'chat_apps_close',
                  l10n.close,
                  symbol: 'xmark',
                  action: (_) => Navigator.of(context).pop(),
                ),
              ],
              sections: [
                NativeSection('chat_apps', [
                  NativeRow(
                    'chat_app_omi',
                    l10n.omiAppName,
                    symbol: isOmiSelected ? 'checkmark.circle.fill' : 'bubble.left',
                    enabled: messageProvider.canSwitchChat,
                    action: (_) => choose('no_selected'),
                  ),
                  for (final app in chatApps) ...[
                    NativeRow(
                      'chat_app_${app.id}',
                      app.getName(),
                      imageUri: nativeImageUri(app.getImageUrl()),
                      symbol: selectedAppId == app.id ? 'checkmark.circle.fill' : null,
                      enabled: messageProvider.canSwitchChat,
                      action: (_) => choose(app.id),
                    ),
                    if (selectedAppId != app.id)
                      NativeRow(
                        'chat_app_disable_${app.id}',
                        l10n.disableAppNamed(app.getName()),
                        destructive: true,
                        enabled: messageProvider.canSwitchChat,
                        action: (_) => onDisableApp(app),
                      ),
                  ],
                  NativeRow(
                    'chat_apps_enable',
                    l10n.enableApps,
                    symbol: 'plus',
                    action: (_) {
                      Navigator.of(context).pop();
                      onEnableApps();
                    },
                  ),
                ]),
                NativeSection('chat_apps_clear', [
                  NativeRow(
                    'chat_apps_clear_action',
                    l10n.clearChat,
                    destructive: true,
                    enabled: messageProvider.canSwitchChat,
                    action: (_) {
                      Navigator.of(context).pop();
                      onClearChat();
                    },
                  ),
                ]),
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
      title: Text(
        name,
        style: OmiType.callout,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: isSelected
          ? ExcludeSemantics(
              child: FaIcon(
                FontAwesomeIcons.solidCircleCheck,
                color: OmiColors.textPrimary,
                size: 18,
              ),
            )
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
      imageBuilder: (context, imageProvider) => CircleAvatar(
        backgroundColor: Colors.white,
        radius: 12,
        backgroundImage: imageProvider,
      ),
      errorWidget: (context, url, error) => CircleAvatar(
        backgroundColor: OmiColors.surface3,
        radius: 12,
        child: Icon(Icons.apps, size: 14, color: OmiColors.textSecondary),
      ),
      placeholder: (context, url) => CircleAvatar(backgroundColor: OmiColors.surface3, radius: 12),
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
        image: DecorationImage(
          image: AssetImage(Assets.images.background.path),
          fit: BoxFit.cover,
        ),
        borderRadius: OmiRadius.lgAll,
      ),
      height: 24,
      width: 24,
      alignment: Alignment.center,
      child: Image.asset(Assets.images.herologo.path, height: 16, width: 16),
    );
  }
}
