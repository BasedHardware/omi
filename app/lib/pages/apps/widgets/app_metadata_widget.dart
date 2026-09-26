import 'dart:io';

import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter_svg/svg.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:skeletonizer/skeletonizer.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/app_form_fields.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AppMetadataWidget extends StatelessWidget {
  final File? imageFile;
  final String? imageUrl;
  final VoidCallback pickImage;
  final TextEditingController appNameController;
  final TextEditingController appDescriptionController;
  final List<Category> categories;
  final Function(String?) setAppCategory;
  final String? category;
  final String? appPricing;
  final bool allowPaidApps;
  final bool generatingDescription;
  const AppMetadataWidget({
    super.key,
    this.imageFile,
    this.imageUrl,
    required this.pickImage,
    required this.appNameController,
    required this.appDescriptionController,
    required this.categories,
    required this.setAppCategory,
    this.category,
    this.appPricing,
    required this.allowPaidApps,
    required this.generatingDescription,
  });

  void _pickCategory(BuildContext context) {
    showAppOptionPicker<String>(
      context: context,
      title: context.l10n.appCategoryModalTitle,
      options: [
        for (final c in categories) AppFormOption<String>(c.id, c.getLocalizedTitle(context)),
      ],
      selected: context.read<AddAppProvider>().appCategory,
      onSelected: setAppCategory,
    );
  }

  void _pickPricing(BuildContext context) {
    final l10n = context.l10n;
    showAppOptionPicker<bool>(
      context: context,
      title: l10n.appPricingLabel,
      options: [
        AppFormOption<bool>(false, l10n.pricingFree),
        AppFormOption<bool>(true, l10n.pricingPaid),
      ],
      selected: context.read<AddAppProvider>().isPaid,
      onSelected: (isPaid) => context.read<AddAppProvider>().setIsPaid(isPaid),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final updateAppId = context.watch<AddAppProvider>().updateAppId;
    return GestureDetector(
      onTap: () {
        FocusScope.of(context).unfocus();
      },
      child: Form(
        key: context.watch<AddAppProvider>().metadataKey,
        onChanged: () {
          Provider.of<AddAppProvider>(context, listen: false).checkValidity();
        },
        child: AppFormCard(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // App ID field with copy button (only shown when updating)
              if (updateAppId != null) ...[
                Padding(
                  padding: const EdgeInsets.only(left: 8.0),
                  child: AppFormSectionTitle(l10n.appIdLabel),
                ),
                Container(
                  margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.xs),
                  decoration: BoxDecoration(
                    borderRadius: OmiRadius.mdAll,
                    border: Border.all(color: OmiColors.border.withValues(alpha: 0.6), width: 1),
                  ),
                  width: double.infinity,
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          updateAppId,
                          style: OmiType.callout.copyWith(color: OmiColors.textSecondary),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      OmiIconButton(
                        icon: const FaIcon(FontAwesomeIcons.copy, size: 16),
                        label: l10n.copyToClipboard,
                        onPressed: () => OmiClipboard.copy(context, updateAppId, what: l10n.appIdLabel),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: OmiSpacing.xs),
              ],
              // Row with Image picker on left, Name and Category on right
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Image picker
                  Stack(
                    clipBehavior: Clip.none,
                    children: [
                      GestureDetector(
                        onTap: pickImage,
                        child: Container(
                          width: 110,
                          height: 105,
                          decoration: BoxDecoration(
                            borderRadius: OmiRadius.lgAll,
                            border: Border.all(color: OmiColors.surface2, width: 2.0),
                          ),
                          child: imageFile != null || imageUrl != null
                              ? (imageUrl == null
                                  ? ClipRRect(
                                      borderRadius: const BorderRadius.all(Radius.circular(14.0)),
                                      child: Image.file(imageFile!, fit: BoxFit.cover),
                                    )
                                  : ClipRRect(
                                      borderRadius: const BorderRadius.all(Radius.circular(14.0)),
                                      child: CachedNetworkImage(imageUrl: imageUrl!, fit: BoxFit.cover),
                                    ))
                              : Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    const FaIcon(FontAwesomeIcons.camera, color: OmiColors.textTertiary, size: 24),
                                    const SizedBox(height: 6),
                                    Text(
                                      '${l10n.appIconLabel}*',
                                      style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                                    ),
                                  ],
                                ),
                        ),
                      ),
                      if (imageFile != null || imageUrl != null)
                        Positioned(
                          bottom: -4,
                          right: -4,
                          child: OmiIconButton.filled(
                            icon: const FaIcon(FontAwesomeIcons.pen, size: 12),
                            fillColor: OmiColors.surface2,
                            diameter: 28,
                            label: l10n.appIconLabel,
                            onPressed: pickImage,
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(width: OmiSpacing.sm + 2),
                  // Name and Category fields
                  Expanded(
                    child: Column(
                      children: [
                        // App Name field
                        TextFormField(
                          validator: (value) {
                            if (value == null || value.isEmpty) {
                              return l10n.pleaseEnterAppName;
                            }
                            return null;
                          },
                          controller: appNameController,
                          decoration: appFormInputDecoration(label: '${l10n.appNameLabel}*'),
                          style: const TextStyle(color: OmiColors.textPrimary),
                        ),
                        const SizedBox(height: OmiSpacing.xs + 2),
                        // Category selector
                        AppFormSelectorField(
                          value: category,
                          placeholder: '${l10n.categoryLabel}*',
                          onTap: () => _pickCategory(context),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: OmiSpacing.sm + 2),
              // Description field (full width)
              Stack(
                children: [
                  generatingDescription
                      ? Container(
                          padding: const EdgeInsets.all(OmiSpacing.md),
                          decoration: BoxDecoration(
                            borderRadius: OmiRadius.mdAll,
                            border: Border.all(color: OmiColors.border.withValues(alpha: 0.6), width: 1),
                          ),
                          constraints: BoxConstraints(minHeight: MediaQuery.sizeOf(context).height * 0.1),
                          child: Skeletonizer.zone(
                            enabled: generatingDescription,
                            effect: const ShimmerEffect(
                              baseColor: OmiColors.surface2,
                              highlightColor: OmiColors.surface3,
                              duration: Duration(seconds: 1),
                            ),
                            child: const Bone.multiText(),
                          ),
                        )
                      : TextFormField(
                          maxLines: null,
                          minLines: 4,
                          validator: (value) {
                            if (value == null || value.isEmpty) {
                              return l10n.pleaseProvideValidDescription;
                            }
                            return null;
                          },
                          controller: appDescriptionController,
                          decoration: appFormInputDecoration(
                            label: '${l10n.descriptionLabel}*',
                            alignLabelWithHint: true,
                          ),
                          style: const TextStyle(color: OmiColors.textPrimary),
                        ),
                  if (appDescriptionController.text.isNotEmpty && appNameController.text.isNotEmpty)
                    Positioned(
                      bottom: 12,
                      right: 12,
                      child: OmiIconButton(
                        icon: SvgPicture.asset(
                          Assets.images.aiMagic,
                          colorFilter: const ColorFilter.mode(OmiColors.textPrimary, BlendMode.srcIn),
                        ),
                        label: l10n.generateDescription,
                        onPressed: () async {
                          await context.read<AddAppProvider>().generateDescription();
                        },
                      ),
                    ),
                ],
              ),
              const SizedBox(height: OmiSpacing.xxs),
              if (allowPaidApps) ...[
                const SizedBox(height: OmiSpacing.xxs),
                AppFormSelectorField(
                  value: appPricing,
                  placeholder: l10n.noneSelected,
                  onTap: () => _pickPricing(context),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
