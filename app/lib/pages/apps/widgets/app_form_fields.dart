import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/media_viewer_page.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

/// Shared pieces of the submit-app and manage-app forms (add_app.dart, update_app.dart and the
/// widgets they embed), so both forms draw their cards, fields and pickers the same way.

/// The outlined text-field decoration every field in the app forms uses.
InputDecoration appFormInputDecoration({String? label, String? hint, bool alignLabelWithHint = false}) {
  final outline = BorderSide(color: OmiColors.border.withValues(alpha: 0.6), width: 1);
  return InputDecoration(
    labelText: label,
    hintText: hint,
    hintMaxLines: 4,
    labelStyle: const TextStyle(color: OmiColors.textTertiary),
    hintStyle: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
    floatingLabelStyle: const TextStyle(color: OmiColors.textSecondary),
    alignLabelWithHint: alignLabelWithHint,
    contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.md),
    border: OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: outline),
    enabledBorder: OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: outline),
    focusedBorder: const OutlineInputBorder(
      borderRadius: OmiRadius.mdAll,
      borderSide: BorderSide(color: OmiColors.textSecondary, width: 1),
    ),
    errorBorder: const OutlineInputBorder(
      borderRadius: OmiRadius.mdAll,
      borderSide: BorderSide(color: OmiColors.danger, width: 1),
    ),
    filled: false,
  );
}

/// A grouped section of an app form: a [OmiColors.surface1] card with large corners.
class AppFormCard extends StatelessWidget {
  const AppFormCard({super.key, required this.child, this.padding = const EdgeInsets.all(14.0)});

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      padding: padding,
      child: child,
    );
  }
}

/// A section title inside an [AppFormCard]; [isRequired] appends a red asterisk.
class AppFormSectionTitle extends StatelessWidget {
  const AppFormSectionTitle(this.text, {super.key, this.isRequired = false});

  final String text;
  final bool isRequired;

  @override
  Widget build(BuildContext context) {
    final style = OmiType.callout.copyWith(color: OmiColors.textSecondary);
    if (!isRequired) return Text(text, style: style);
    return Text.rich(
      TextSpan(
        text: text,
        style: style,
        children: const [TextSpan(text: ' *', style: TextStyle(color: OmiColors.danger))],
      ),
    );
  }
}

/// The question-mark control next to a section title that opens the developer docs.
class AppFormDocsButton extends StatelessWidget {
  const AppFormDocsButton({super.key, required this.url});

  final String url;

  @override
  Widget build(BuildContext context) {
    return OmiIconButton(
      icon: const FaIcon(FontAwesomeIcons.solidCircleQuestion, size: 18),
      color: OmiColors.textTertiary,
      label: context.l10n.docs,
      onPressed: () => launchUrl(Uri.parse(url)),
    );
  }
}

/// A read-only field that opens a picker: the chosen [value] (or the [placeholder]) and a chevron.
class AppFormSelectorField extends StatelessWidget {
  const AppFormSelectorField({
    super.key,
    required this.value,
    required this.placeholder,
    required this.onTap,
    this.margin = EdgeInsets.zero,
  });

  final String? value;
  final String placeholder;
  final VoidCallback onTap;
  final EdgeInsetsGeometry margin;

  @override
  Widget build(BuildContext context) {
    final hasValue = value?.isNotEmpty == true;
    return Padding(
      padding: margin,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: OmiRadius.mdAll,
          child: Container(
            constraints: const BoxConstraints(minHeight: 48),
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 14.0),
            decoration: BoxDecoration(
              borderRadius: OmiRadius.mdAll,
              border: Border.all(color: OmiColors.border.withValues(alpha: 0.6), width: 1),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    hasValue ? value! : placeholder,
                    style: OmiType.callout.copyWith(
                      color: hasValue ? OmiColors.textPrimary : OmiColors.textTertiary,
                    ),
                  ),
                ),
                const FaIcon(FontAwesomeIcons.chevronRight, color: OmiColors.textTertiary, size: 14),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// One choice in [showAppOptionPicker].
class AppFormOption<T> {
  const AppFormOption(this.value, this.label);

  final T value;
  final String label;
}

/// Shows a single-choice list in an Omi sheet. Picking a row calls [onSelected] and closes it.
Future<void> showAppOptionPicker<T>({
  required BuildContext context,
  required String title,
  required List<AppFormOption<T>> options,
  required T? selected,
  required ValueChanged<T> onSelected,
}) {
  return showOmiSheet<void>(
    context: context,
    title: title,
    builder: (sheetContext) => ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(sheetContext).height * 0.6),
      child: ListView.separated(
        shrinkWrap: true,
        itemCount: options.length,
        separatorBuilder: (_, __) => const Divider(color: OmiColors.border, height: 1),
        itemBuilder: (itemContext, index) {
          final option = options[index];
          final isSelected = option.value == selected;
          void pick() {
            onSelected(option.value);
            Navigator.of(sheetContext).pop();
          }

          return Semantics(
            selected: isSelected,
            child: InkWell(
              onTap: pick,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xxs, horizontal: 6),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(option.label, style: OmiType.callout.copyWith(color: OmiColors.textSecondary)),
                    ),
                    Checkbox(
                      value: isSelected,
                      onChanged: (_) => pick(),
                      side: const BorderSide(color: OmiColors.textSecondary),
                      shape: const CircleBorder(),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    ),
  );
}

/// Opens an app's screenshots full screen, as a modal with a close X.
void openAppScreenshots(BuildContext context, List<String> urls, int initialIndex) {
  // The one media viewer presentation: a full-screen modal with a trailing close and swipe-down.
  MediaViewerPage.open(
    context,
    items: urls.map((url) => MediaViewerItem(imageUrl: url)).toList(),
    initialIndex: initialIndex,
    maxScaleMultiplier: 2,
    wrapBodyInSafeArea: false,
  );
}

/// The "Preview screenshots" card of the app forms: a horizontal strip of 2:3 thumbnails, each
/// opening the viewer and carrying a remove control, and an add tile at the end.
///
/// With [collapseWhenEmpty] the card shows only its title and an add control until the first
/// screenshot is added (the submit form); otherwise the add tile is always in the strip.
class AppScreenshotsSection extends StatelessWidget {
  const AppScreenshotsSection({
    super.key,
    required this.title,
    required this.urls,
    required this.isUploading,
    required this.onAdd,
    required this.onRemove,
    this.collapseWhenEmpty = false,
  });

  static const double _width = 120;
  static const double _height = _width * 1.5;

  final String title;
  final List<String> urls;
  final bool isUploading;
  final VoidCallback onAdd;
  final ValueChanged<int> onRemove;
  final bool collapseWhenEmpty;

  @override
  Widget build(BuildContext context) {
    final collapsed = collapseWhenEmpty && urls.isEmpty;
    return AppFormCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Padding(padding: const EdgeInsets.only(left: 8), child: AppFormSectionTitle(title)),
              if (collapsed)
                isUploading
                    ? const SizedBox(
                        width: kOmiMinTapTarget,
                        height: kOmiMinTapTarget,
                        child: Center(child: OmiSpinner(size: OmiSpinnerSize.small)),
                      )
                    : OmiIconButton.filled(
                        icon: const FaIcon(FontAwesomeIcons.image, size: 16),
                        fillColor: OmiColors.surface3,
                        label: context.l10n.addScreenshot,
                        onPressed: onAdd,
                      ),
            ],
          ),
          if (!collapsed)
            SizedBox(
              height: _height + OmiSpacing.md + OmiSpacing.xs,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(8, OmiSpacing.md, 8, OmiSpacing.xs),
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  itemCount: urls.length + 1,
                  itemBuilder: (context, index) {
                    if (index == urls.length) return _addTile(context);
                    return _thumbnail(context, index);
                  },
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _addTile(BuildContext context) {
    return Semantics(
      button: true,
      label: context.l10n.addScreenshot,
      child: GestureDetector(
        onTap: isUploading ? null : onAdd,
        child: Container(
          width: _width,
          height: _height,
          margin: const EdgeInsets.only(right: 8),
          decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
          child: Center(
            child: isUploading
                ? const OmiSpinner(size: OmiSpinnerSize.small)
                : const FaIcon(FontAwesomeIcons.image, size: 28, color: OmiColors.textPrimary),
          ),
        ),
      ),
    );
  }

  Widget _thumbnail(BuildContext context, int index) {
    Widget frame({Color? color, DecorationImage? image, Widget? child, bool bordered = false}) => Container(
          width: _width,
          height: _height,
          margin: const EdgeInsets.only(right: 8),
          decoration: BoxDecoration(
            color: color,
            borderRadius: OmiRadius.smAll,
            border: bordered ? Border.all(color: OmiColors.border, width: 1) : null,
            image: image,
          ),
          child: child,
        );

    return Stack(
      children: [
        Semantics(
          button: true,
          label: context.l10n.previewImageLabel(index + 1, urls.length),
          child: GestureDetector(
            onTap: () => openAppScreenshots(context, urls, index),
            child: CachedNetworkImage(
              imageUrl: urls[index],
              imageBuilder: (context, imageProvider) =>
                  frame(bordered: true, image: DecorationImage(image: imageProvider, fit: BoxFit.cover)),
              placeholder: (context, url) => ShimmerWithTimeout(
                baseColor: OmiColors.surface1,
                highlightColor: OmiColors.surface2,
                child: frame(color: OmiColors.surface0),
              ),
              errorWidget: (context, url, error) => frame(
                color: OmiColors.surface1,
                child: const Center(child: FaIcon(FontAwesomeIcons.triangleExclamation)),
              ),
            ),
          ),
        ),
        Positioned(
          top: 0,
          right: 8,
          child: OmiIconButton.filled(
            icon: const FaIcon(FontAwesomeIcons.xmark, size: 12),
            color: OmiColors.onAccent,
            fillColor: OmiColors.accent,
            diameter: 22,
            label: context.l10n.removeScreenshot,
            onPressed: () => onRemove(index),
          ),
        ),
      ],
    );
  }
}

/// The "GitHub Repository URL" card of the app forms (required for external integrations and
/// proactive notifications).
class AppSourceCodeUrlSection extends StatelessWidget {
  const AppSourceCodeUrlSection({super.key, required this.controller});

  final TextEditingController controller;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return AppFormCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 8),
            child: AppFormSectionTitle(l10n.githubRepositoryUrl, isRequired: true),
          ),
          const SizedBox(height: OmiSpacing.xxs),
          Padding(
            padding: const EdgeInsets.only(left: 8),
            child: Text(l10n.githubRepositoryUrlHint, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
          ),
          const SizedBox(height: OmiSpacing.sm),
          TextFormField(
            controller: controller,
            // An example value, not prose: the same in every language.
            decoration: appFormInputDecoration(hint: 'https://github.com/username/repo'),
            style: const TextStyle(color: OmiColors.textPrimary),
            keyboardType: TextInputType.url,
            validator: (value) {
              if (value == null || value.trim().isEmpty) return l10n.githubRepositoryUrlRequired;
              if (!(Uri.tryParse(value.trim())?.isAbsolute ?? false)) return l10n.invalidUrlError;
              return null;
            },
          ),
        ],
      ),
    );
  }
}
