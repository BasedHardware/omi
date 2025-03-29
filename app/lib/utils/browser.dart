import 'package:flutter/material.dart';
import 'package:flutter_custom_tabs/flutter_custom_tabs.dart';

Future<void> launchCustomTab(BuildContext context, String url, {CustomTabsSession? session}) async {
  final theme = Theme.of(context);
  final mediaQuery = MediaQuery.of(context);
  await launchUrl(
    Uri.parse(url),
    customTabsOptions: CustomTabsOptions(
      partial: PartialCustomTabsConfiguration(
        initialHeight: mediaQuery.size.height - 300,
        activityHeightResizeBehavior: CustomTabsActivityHeightResizeBehavior.adjustable,
      ),
      colorSchemes: CustomTabsColorSchemes.defaults(
        colorScheme: theme.brightness.toColorScheme(),
        toolbarColor: theme.colorScheme.primary,
      ),
      showTitle: false,
      urlBarHidingEnabled: true,
      shareState: CustomTabsShareState.off,
      browser: session != null ? CustomTabsBrowserConfiguration.session(session) : null,
      closeButton:
          CustomTabsCloseButton(icon: CustomTabsCloseButtonIcons.back, position: CustomTabsCloseButtonPosition.end),
    ),
    safariVCOptions: const SafariViewControllerOptions(
      pageSheet: SheetPresentationControllerConfiguration(
        detents: {
          SheetPresentationControllerDetent.large,
        },
        prefersScrollingExpandsWhenScrolledToEdge: true,
        prefersGrabberVisible: true,
        prefersEdgeAttachedInCompactHeight: true,
        preferredCornerRadius: 16.0,
      ),
      modalPresentationStyle: ViewControllerModalPresentationStyle.pageSheet,
      entersReaderIfAvailable: false,
      dismissButtonStyle: SafariViewControllerDismissButtonStyle.close,
    ),
  );
}
