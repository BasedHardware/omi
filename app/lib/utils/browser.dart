import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_custom_tabs/flutter_custom_tabs.dart';

Future<void> launchCustomTab(BuildContext context, String url, {CustomTabsSession? session}) async {
  final theme = Theme.of(context);
  final mediaQuery = MediaQuery.of(context);
  await launchUrl(
    Uri.parse(url),
    customTabsOptions: CustomTabsOptions.partial(
      configuration: PartialCustomTabsConfiguration(
        initialHeight: mediaQuery.size.height,
      ),
      colorSchemes: CustomTabsColorSchemes.defaults(
        colorScheme: theme.brightness.toColorScheme(),
        toolbarColor: theme.colorScheme.primary,
      ),
      showTitle: false,
      shareState: CustomTabsShareState.off,
      browser: session != null ? CustomTabsBrowserConfiguration.session(session) : null,
      closeButton: CustomTabsCloseButton(icon: CustomTabsCloseButtonIcons.back),
    ),
    safariVCOptions: SafariViewControllerOptions.pageSheet(
      configuration: const SheetPresentationControllerConfiguration(
        detents: {
          SheetPresentationControllerDetent.large,
          SheetPresentationControllerDetent.medium,
        },
        prefersScrollingExpandsWhenScrolledToEdge: true,
        prefersGrabberVisible: true,
        prefersEdgeAttachedInCompactHeight: true,
        preferredCornerRadius: 48.0,
      ),
      preferredBarTintColor: theme.colorScheme.primary,
      preferredControlTintColor: theme.colorScheme.onPrimary,
      entersReaderIfAvailable: true,
      dismissButtonStyle: SafariViewControllerDismissButtonStyle.close,
    ),
  );
}
