import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/services/integrations/integration_oauth.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Login-capable external pages use the system browser, including Google popups.
class OmiExternalBrowserPage extends StatefulWidget {
  const OmiExternalBrowserPage({super.key, required this.title, required this.url, this.message, this.openKey});
  final String title;
  final Uri url;
  final String? message;
  final Key? openKey;

  @override
  State<OmiExternalBrowserPage> createState() => _OmiExternalBrowserPageState();
}

class _OmiExternalBrowserPageState extends State<OmiExternalBrowserPage> {
  bool _opening = false;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_openBrowser());
    });
  }

  Future<void> _openBrowser() async {
    if (_opening) return;
    setState(() {
      _opening = true;
      _failed = false;
    });
    final opened = await launchIntegrationOAuth(
      () async => widget.url.toString(),
      deadline: const Duration(seconds: 15),
      isCurrent: () => mounted,
    );
    if (!mounted) return;
    setState(() {
      _opening = false;
      _failed = !opened;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(widget.title)),
      body: SafeArea(
        child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
                  child: ConstrainedBox(
                    constraints: BoxConstraints(minHeight: constraints.maxHeight),
                    child: _failed
                        ? OmiErrorState(message: context.l10n.failedToStartAuth(widget.title), onRetry: _openBrowser)
                        : OmiEmptyState(
                            icon: Icons.open_in_browser,
                            title: widget.title,
                            message: widget.message ?? widget.url.host,
                            action: OmiButton(
                              key: widget.openKey,
                              label: context.l10n.open,
                              isLoading: _opening,
                              onPressed: _openBrowser,
                            ),
                          ),
                  ),
                )),
      ),
    );
  }
}
