import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:provider/provider.dart';

typedef AppSelectionCallback = void Function(String? value, AppProvider provider);

class AppSelectionDropdown extends StatefulWidget {
  final AppSelectionCallback? onAppSelected;
  final VoidCallback? onClearChat;
  final VoidCallback? onEnableApps;
  final bool isFloating;

  const AppSelectionDropdown({
    super.key,
    this.onAppSelected,
    this.onClearChat,
    this.onEnableApps,
    this.isFloating = true,
  });

  @override
  State<AppSelectionDropdown> createState() => _AppSelectionDropdownState();
}

class _AppSelectionDropdownState extends State<AppSelectionDropdown> with TickerProviderStateMixin {
  final GlobalKey _appButtonKey = GlobalKey();

  void _handleAppSelection(String? val, AppProvider provider) {
    if (val == null || val == provider.selectedChatAppId) {
      return;
    }

    // clear chat
    if (val == 'clear_chat') {
      _showClearChatDialog();
      return;
    }

    // enable apps - navigate back to home and show apps page
    if (val == 'enable') {
      _navigateToAppsPage();
      return;
    }

    // select app by id
    _selectApp(val, provider);
  }

  void _showClearChatDialog() {
    if (!mounted) return;

    showDialog(
      context: context,
      builder: (ctx) {
        return getDialog(context, () {
          Navigator.of(context).pop();
        }, () {
          if (mounted) {
            context.read<MessageProvider>().clearChat();
            Navigator.of(context).pop();
          }
          widget.onClearChat?.call();
        }, "Clear Chat?", "Are you sure you want to clear the chat? This action cannot be undone.");
      },
    );
  }

  void _navigateToAppsPage() {
    if (!mounted) return;

    MixpanelManager().pageOpened('Chat Apps');
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (context) => const HomePageWrapper(navigateToRoute: '/apps'),
      ),
    );
    widget.onEnableApps?.call();
  }

  void _selectApp(String appId, AppProvider appProvider) async {
    if (!mounted) return;

    // Store references before async operation
    final messageProvider = mounted ? context.read<MessageProvider>() : null;
    if (messageProvider == null) return;

    // Set the selected app
    appProvider.setSelectedChatAppId(appId);

    // Add a small delay to let the keyboard animation complete
    // This prevents the widget from being unmounted during the keyboard transition
    await Future.delayed(const Duration(milliseconds: 100));

    // Check if widget is still mounted after delay
    if (!mounted) return;

    // Perform async operation
    await messageProvider.refreshMessages(dropdownSelected: true);

    // Check if widget is still mounted before proceeding
    if (!mounted) return;

    // Get the selected app and send initial message if needed
    var app = appProvider.getSelectedApp();
    if (messageProvider.messages.isEmpty) {
      messageProvider.sendInitialAppMessage(app);
    }

    widget.onAppSelected?.call(appId, appProvider);
  }

  void _showAppsMenu(BuildContext ctx, AppProvider provider) {
    final renderBox = _appButtonKey.currentContext?.findRenderObject() as RenderBox?;
    if (renderBox == null) return;

    final overlay = Overlay.of(ctx, rootOverlay: true);

    final buttonOffset = renderBox.localToGlobal(Offset.zero);
    final buttonSize = renderBox.size;
    final screenSize = MediaQuery.of(ctx).size;

    const double menuWidth = 260;
    const double maxMenuHeight = 250;

    double desiredTop = buttonOffset.dy + buttonSize.height + 8;
    if ((desiredTop + maxMenuHeight) > screenSize.height) {
      desiredTop = buttonOffset.dy - maxMenuHeight - 8;
      if (desiredTop < 0) desiredTop = 8;
    }

    late OverlayEntry entry;

    final controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
    );
    final curved = CurvedAnimation(parent: controller, curve: Curves.easeOut);

    entry = OverlayEntry(
      builder: (context) {
        return Consumer<MessageProvider>(
          builder: (context, msgProvider, _) {
            return Stack(
              children: [
                Positioned.fill(
                  child: GestureDetector(
                    behavior: HitTestBehavior.translucent,
                    onTap: () {
                      controller.reverse().then((_) => entry.remove());
                    },
                    child: Container(color: Colors.transparent),
                  ),
                ),
                Positioned(
                  left: buttonOffset.dx + (buttonSize.width - menuWidth) / 2,
                  top: desiredTop,
                  child: AnimatedBuilder(
                    animation: curved,
                    builder: (context, child) {
                      return Transform.scale(
                        scale: curved.value,
                        alignment: Alignment.topCenter,
                        child: Opacity(
                          opacity: curved.value,
                          child: child,
                        ),
                      );
                    },
                    child: Material(
                      color: Colors.grey[900],
                      borderRadius: BorderRadius.circular(12),
                      elevation: 8,
                      child: SizedBox(
                        width: menuWidth,
                        height: maxMenuHeight,
                        child: PullDownMenu(
                          items: [
                            PullDownMenuItem(
                              title: 'Clear Chat',
                              iconWidget: const Icon(Icons.delete, color: Colors.redAccent, size: 16),
                              onTap: () {
                                controller.reverse().then((_) {
                                  entry.remove();
                                  _handleAppSelection('clear_chat', provider);
                                });
                              },
                            ),
                            PullDownMenuItem(
                              title: 'Enable Apps',
                              iconWidget: const Icon(Icons.arrow_forward_ios, color: Colors.white60, size: 16),
                              onTap: () {
                                controller.reverse().then((_) {
                                  entry.remove();
                                  _handleAppSelection('enable', provider);
                                });
                              },
                            ),
                            PullDownMenuItem(
                              title: 'Omi',
                              iconWidget: _getOmiAvatar(),
                              onTap: () {
                                controller.reverse().then((_) {
                                  entry.remove();
                                  _handleAppSelection('no_selected', provider);
                                });
                              },
                              subtitle:
                                  msgProvider.chatApps.firstWhereOrNull((a) => a.id == provider.selectedChatAppId) ==
                                          null
                                      ? 'Selected'
                                      : null,
                            ),
                            ...msgProvider.chatApps.map(
                              (app) => PullDownMenuItem(
                                title: app.getName(),
                                iconWidget: _getAppAvatar(app),
                                onTap: () {
                                  controller.reverse().then((_) {
                                    entry.remove();
                                    _handleAppSelection(app.id, provider);
                                  });
                                },
                                subtitle: provider.selectedChatAppId == app.id ? 'Selected' : null,
                              ),
                            )
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            );
          },
        );
      },
    );

    overlay.insert(entry);
    controller.forward();
  }

  Widget _buildAppSelection(BuildContext context, AppProvider provider) {
    final messageProvider = Provider.of<MessageProvider>(context, listen: false);
    var selectedApp = messageProvider.chatApps.firstWhereOrNull((app) => app.id == provider.selectedChatAppId);

    return GestureDetector(
      key: _appButtonKey,
      onTap: () {
        HapticFeedback.mediumImpact();
        _showAppsMenu(context, provider);
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: widget.isFloating
            ? BoxDecoration(
                color: Colors.black.withOpacity(0.7),
                borderRadius: BorderRadius.circular(30),
                border: Border.all(
                  color: Colors.white.withOpacity(0.15),
                  width: 1,
                ),
              )
            : BoxDecoration(
                color: Colors.black.withOpacity(0.6),
                borderRadius: BorderRadius.circular(30),
                border: Border.all(
                  color: Colors.white.withOpacity(0.2),
                  width: 1,
                ),
              ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            selectedApp != null ? _getAppAvatar(selectedApp) : _getOmiAvatar(),
            const SizedBox(width: 10),
            Container(
              constraints: const BoxConstraints(maxWidth: 100),
              child: Text(
                selectedApp != null ? selectedApp.getName() : "Omi",
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w500,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 8),
            const Icon(
              Icons.keyboard_arrow_down,
              color: Colors.white70,
              size: 18,
            ),
          ],
        ),
      ),
    );
  }

  Widget _getAppAvatar(App app) {
    return CachedNetworkImage(
      imageUrl: app.getImageUrl(),
      imageBuilder: (context, imageProvider) {
        return CircleAvatar(
          backgroundColor: Colors.white,
          radius: 12,
          backgroundImage: imageProvider,
        );
      },
      errorWidget: (context, url, error) {
        return const CircleAvatar(
          backgroundColor: Colors.white,
          radius: 12,
          child: Icon(Icons.error_outline_rounded),
        );
      },
      progressIndicatorBuilder: (context, url, progress) => CircleAvatar(
        backgroundColor: Colors.white,
        radius: 12,
        child: CircularProgressIndicator(
          value: progress.progress,
          valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
        ),
      ),
    );
  }

  Widget _getOmiAvatar() {
    return Container(
      decoration: BoxDecoration(
        image: DecorationImage(
          image: AssetImage(Assets.images.background.path),
          fit: BoxFit.cover,
        ),
        borderRadius: const BorderRadius.all(Radius.circular(16.0)),
      ),
      height: 24,
      width: 24,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Image.asset(
            Assets.images.herologo.path,
            height: 16,
            width: 16,
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppProvider>(
      builder: (context, appProvider, child) {
        return _buildAppSelection(context, appProvider);
      },
    );
  }
}
