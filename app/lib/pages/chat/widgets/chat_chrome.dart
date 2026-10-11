import 'package:flutter/material.dart';
import 'package:flutter/gestures.dart';
import 'package:collection/collection.dart';
import 'package:provider/provider.dart';
import 'package:omi/pages/chat/chat_route.dart';
import 'package:omi/pages/chat/widgets/chat_apps_drawer.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class ChatHeader extends StatelessWidget implements PreferredSizeWidget {
  const ChatHeader({super.key, required this.provider});
  final MessageProvider provider;
  @override
  Size get preferredSize => Size.fromHeight(kToolbarHeight + (provider.isLoadingMessages ? 32 : 0));

  @override
  Widget build(BuildContext context) {
    final appId = context.watch<AppProvider>().selectedChatAppId;
    final app = provider.chatApps.firstWhereOrNull((app) => app.id == appId);
    return AppBar(
      elevation: 0,
      scrolledUnderElevation: 0,
      backgroundColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      automaticallyImplyLeading: false,
      leading: const Center(child: OmiCloseButton.circled(key: Key('chat_close'))),
      centerTitle: true,
      title: _ChatDismissRegion(
          child: app == null
              ? Semantics(
                  label: context.l10n.askOmi,
                  header: true,
                  child: Container(
                      width: 36,
                      height: 4,
                      decoration: BoxDecoration(color: OmiColors.border, borderRadius: OmiRadius.pillAll)))
              : Row(mainAxisSize: MainAxisSize.min, children: [
                  ChatAppAvatar(app: app),
                  const SizedBox(width: OmiSpacing.xs),
                  Flexible(child: Text(app.getName(), overflow: TextOverflow.ellipsis, style: OmiType.callout)),
                ])),
      // Balance the close control so the dismissal handle stays centered without a history button.
      actions: const [SizedBox(width: kToolbarHeight)],
      bottom: provider.isLoadingMessages
          ? PreferredSize(
              preferredSize: const Size.fromHeight(32),
              child: SizedBox(
                  height: 32,
                  child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    const OmiSpinner(size: OmiSpinnerSize.small),
                    const SizedBox(width: OmiSpacing.xs),
                    Flexible(child: Text(context.l10n.syncingMessages, style: OmiType.footnote)),
                  ])),
            )
          : null,
    );
  }
}

/// Only the header owns dismissal, so reading or selecting transcript text cannot close chat.
class _ChatDismissRegion extends StatefulWidget {
  const _ChatDismissRegion({required this.child});
  final Widget child;

  @override
  State<_ChatDismissRegion> createState() => _ChatDismissRegionState();
}

class _ChatDismissRegionState extends State<_ChatDismissRegion> {
  ChatSheetRoute<dynamic>? _route;

  void _finish(double velocity, {bool cancelled = false}) {
    final route = _route;
    _route = null;
    route?.finishDismissDrag(velocity, cancelled: cancelled);
  }

  @override
  Widget build(BuildContext context) => GestureDetector(
        key: const Key('chat_drag_handle'),
        behavior: HitTestBehavior.opaque,
        dragStartBehavior: DragStartBehavior.down,
        onVerticalDragStart: (_) {
          final route = ModalRoute.of(context);
          if (route is ChatSheetRoute &&
              route.startDismissDrag(
                  extent: MediaQuery.sizeOf(context).height, reduceMotion: MediaQuery.disableAnimationsOf(context))) {
            _route = route;
          }
        },
        onVerticalDragUpdate: (details) => _route?.updateDismissDrag(details.primaryDelta ?? 0),
        onVerticalDragCancel: () => _finish(0, cancelled: true),
        onVerticalDragEnd: (details) => _finish(details.primaryVelocity ?? 0),
        child: SizedBox(width: double.infinity, height: kToolbarHeight, child: Center(child: widget.child)),
      );
}

class ChatOfflineHint extends StatelessWidget {
  const ChatOfflineHint({super.key});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ExcludeSemantics(child: Icon(Icons.cloud_off_rounded, size: 14, color: OmiColors.textTertiary)),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                context.l10n.chatOfflineHint,
                style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                textAlign: TextAlign.center,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
