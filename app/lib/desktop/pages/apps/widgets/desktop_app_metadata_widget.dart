import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter_svg/svg.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:skeletonizer/skeletonizer.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopAppMetadataWidget extends StatelessWidget {
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

  const DesktopAppMetadataWidget({
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

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        FocusScope.of(context).unfocus();
      },
      child: Form(
        key: context.watch<AddAppProvider>().metadataKey,
        onChanged: () {
          Provider.of<AddAppProvider>(context, listen: false).checkValidity();
        },
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Stack(
                children: [
                  GestureDetector(
                    onTap: pickImage,
                    child: Container(
                      width: 120,
                      height: 120,
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(
                          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                          width: 2,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.1),
                            blurRadius: 8,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: imageFile != null || imageUrl != null
                          ? ClipRRect(
                              borderRadius: BorderRadius.circular(22),
                              child: imageUrl == null
                                  ? Image.file(imageFile!, fit: BoxFit.cover)
                                  : CachedNetworkImage(
                                      imageUrl: imageUrl!,
                                      fit: BoxFit.cover,
                                      placeholder: (context, url) => Container(
                                        decoration: BoxDecoration(
                                          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
                                          borderRadius: BorderRadius.circular(22),
                                        ),
                                        child: const Center(
                                          child: CircularProgressIndicator(
                                            valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
                                            strokeWidth: 2,
                                          ),
                                        ),
                                      ),
                                      errorWidget: (context, url, error) => const Icon(
                                        FontAwesomeIcons.image,
                                        color: ResponsiveHelper.textTertiary,
                                        size: 32,
                                      ),
                                    ),
                            )
                          : const Icon(
                              FontAwesomeIcons.plus,
                              color: ResponsiveHelper.textTertiary,
                              size: 32,
                            ),
                    ),
                  ),
                  if (imageFile != null || imageUrl != null)
                    Positioned(
                      bottom: 0,
                      right: 0,
                      child: GestureDetector(
                        onTap: pickImage,
                        child: Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.purplePrimary,
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
                                blurRadius: 8,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: const Icon(
                            FontAwesomeIcons.pen,
                            color: Colors.white,
                            size: 12,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),

            const SizedBox(height: 32),

            // Form fields
            // App ID field (if updating)
            if (context.watch<AddAppProvider>().updateAppId != null) ...[
              _buildFieldLabel(context, context.l10n.appIdLabel),
              const SizedBox(height: 8),
              _buildAppIdField(context),
              const SizedBox(height: 20),
            ],

            // App Name field
            _buildFieldLabel(context, context.l10n.appNameLabel),
            const SizedBox(height: 8),
            _buildTextField(
              context: context,
              controller: appNameController,
              hintText: context.l10n.appNamePlaceholder,
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return context.l10n.pleaseEnterAppName;
                }
                return null;
              },
            ),

            const SizedBox(height: 20),

            // Category field
            _buildFieldLabel(context, context.l10n.categoryLabel),
            const SizedBox(height: 8),
            _buildCategoryDropdown(context),

            const SizedBox(height: 20),

            // Description field
            _buildFieldLabel(context, context.l10n.descriptionLabel),
            const SizedBox(height: 8),
            _buildDescriptionField(context),

            // App Pricing field (if allowed)
            if (allowPaidApps) ...[
              const SizedBox(height: 20),
              _buildFieldLabel(context, context.l10n.appPricingLabel),
              const SizedBox(height: 8),
              _buildPricingDropdown(context),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildFieldLabel(BuildContext context, String label) {
    return Text(
      label,
      style: const TextStyle(
        color: ResponsiveHelper.textSecondary,
        fontSize: 14,
        fontWeight: FontWeight.w500,
      ),
    );
  }

  Widget _buildTextField({
    required BuildContext context,
    required TextEditingController controller,
    required String hintText,
    String? Function(String?)? validator,
    int maxLines = 1,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: TextFormField(
        controller: controller,
        validator: validator,
        maxLines: maxLines,
        style: const TextStyle(
          color: ResponsiveHelper.textPrimary,
          fontSize: 14,
        ),
        decoration: InputDecoration(
          hintText: hintText,
          hintStyle: const TextStyle(
            color: ResponsiveHelper.textTertiary,
            fontSize: 14,
          ),
          border: InputBorder.none,
          contentPadding: const EdgeInsets.all(16),
          isDense: true,
        ),
      ),
    );
  }

  Widget _buildAppIdField(BuildContext context) {
    final appId = context.watch<AddAppProvider>().updateAppId!;

    return Container(
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Expanded(
            child: Text(
              appId,
              style: const TextStyle(
                color: ResponsiveHelper.textTertiary,
                fontSize: 14,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 12),
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () {
                Clipboard.setData(ClipboardData(text: appId));
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(context.l10n.appIdCopiedToClipboard),
                    backgroundColor: ResponsiveHelper.purplePrimary,
                    behavior: SnackBarBehavior.floating,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    duration: const Duration(seconds: 2),
                  ),
                );
              },
              borderRadius: BorderRadius.circular(8),
              child: Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(
                  FontAwesomeIcons.copy,
                  color: ResponsiveHelper.textSecondary,
                  size: 14,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCategoryDropdown(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => _showCategoryModal(context),
        borderRadius: BorderRadius.circular(12),
        child: Container(
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
              width: 1,
            ),
          ),
          padding: const EdgeInsets.all(16),
          child: Builder(
            builder: (context) => Row(
              children: [
                Expanded(
                  child: Text(
                    category?.isNotEmpty == true ? category! : context.l10n.selectCategory,
                    style: TextStyle(
                      color: category?.isNotEmpty == true ? ResponsiveHelper.textPrimary : ResponsiveHelper.textTertiary,
                      fontSize: 14,
                    ),
                  ),
                ),
                const Icon(
                  FontAwesomeIcons.chevronDown,
                  color: ResponsiveHelper.textTertiary,
                  size: 12,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDescriptionField(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: Stack(
        children: [
          ConstrainedBox(
            constraints: const BoxConstraints(
              minHeight: 120,
              maxHeight: 200,
            ),
            child: Scrollbar(
              child: generatingDescription
                  ? Skeletonizer.zone(
                      enabled: generatingDescription,
                      effect: const ShimmerEffect(
                        baseColor: ResponsiveHelper.backgroundTertiary,
                        highlightColor: ResponsiveHelper.backgroundSecondary,
                        duration: Duration(seconds: 1),
                      ),
                      child: Container(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: List.generate(
                            4,
                            (index) => Container(
                              width: index == 3 ? 200 : double.infinity,
                              height: 16,
                              margin: const EdgeInsets.only(bottom: 8),
                              decoration: BoxDecoration(
                                color: ResponsiveHelper.backgroundTertiary,
                                borderRadius: BorderRadius.circular(4),
                              ),
                            ),
                          ),
                        ),
                      ),
                    )
                  : Builder(
                      builder: (context) => TextFormField(
                        controller: appDescriptionController,
                        maxLines: null,
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return context.l10n.pleaseProvideValidDescription;
                          }
                          return null;
                        },
                        style: const TextStyle(
                          color: ResponsiveHelper.textPrimary,
                          fontSize: 14,
                          height: 1.5,
                        ),
                        decoration: InputDecoration(
                          hintText: context.l10n.appDescriptionPlaceholder,
                          hintStyle: const TextStyle(
                            color: ResponsiveHelper.textTertiary,
                            fontSize: 14,
                          ),
                          border: InputBorder.none,
                          contentPadding: const EdgeInsets.all(16),
                          isDense: false,
                        ),
                      ),
                    ),
            ),
          ),
          if (appDescriptionController.text.isNotEmpty && appNameController.text.isNotEmpty)
            Positioned(
              bottom: 8,
              right: 8,
              child: Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: () async {
                    await context.read<AddAppProvider>().generateDescription();
                  },
                  borderRadius: BorderRadius.circular(8),
                  child: Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
                        width: 1,
                      ),
                    ),
                    child: SvgPicture.asset(
                      Assets.images.aiMagic,
                      color: ResponsiveHelper.purplePrimary,
                      width: 16,
                      height: 16,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildPricingDropdown(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => _showPricingModal(context),
        borderRadius: BorderRadius.circular(12),
        child: Container(
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
              width: 1,
            ),
          ),
          padding: const EdgeInsets.all(16),
          child: Builder(
            builder: (context) => Row(
              children: [
                Expanded(
                  child: Text(
                    appPricing?.isNotEmpty == true ? appPricing! : context.l10n.noneSelected,
                    style: TextStyle(
                      color:
                          appPricing?.isNotEmpty == true ? ResponsiveHelper.textPrimary : ResponsiveHelper.textTertiary,
                      fontSize: 14,
                    ),
                  ),
                ),
                const Icon(
                  FontAwesomeIcons.chevronDown,
                  color: ResponsiveHelper.textTertiary,
                  size: 12,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _showCategoryModal(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => Container(
        height: MediaQuery.of(context).size.height * 0.6,
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: const BorderRadius.vertical(
            top: Radius.circular(20),
          ),
          border: Border.all(
            color: ResponsiveHelper.backgroundTertiary,
            width: 1,
          ),
        ),
        child: Column(
          children: [
            // Handle bar
            Container(
              margin: const EdgeInsets.only(top: 8),
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: ResponsiveHelper.textQuaternary,
                borderRadius: BorderRadius.circular(2),
              ),
            ),

            // Header
            Padding(
              padding: const EdgeInsets.all(20),
              child: Row(
                children: [
                  const Icon(
                    FontAwesomeIcons.tag,
                    color: ResponsiveHelper.textSecondary,
                    size: 18,
                  ),
                  const SizedBox(width: 12),
                  Text(
                    context.l10n.appCategoryModalTitle,
                    style: const TextStyle(
                      color: ResponsiveHelper.textPrimary,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),

            // Categories list
            Expanded(
              child: ListView.separated(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                separatorBuilder: (context, index) => Container(
                  height: 1,
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                ),
                itemCount: categories.length,
                itemBuilder: (context, index) {
                  final categoryItem = categories[index];
                  final isSelected = context.watch<AddAppProvider>().appCategory == categoryItem.id;

                  return Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () {
                        context.read<AddAppProvider>().setAppCategory(categoryItem.id);
                        Navigator.pop(context);
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                categoryItem.title,
                                style: const TextStyle(
                                  color: ResponsiveHelper.textPrimary,
                                  fontSize: 16,
                                ),
                              ),
                            ),
                            if (isSelected)
                              const Icon(
                                FontAwesomeIcons.check,
                                color: ResponsiveHelper.purplePrimary,
                                size: 16,
                              ),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showPricingModal(BuildContext context) {
    final options = [context.l10n.pricingFree, context.l10n.pricingPaid];

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => Container(
        height: MediaQuery.of(context).size.height * 0.36,
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: const BorderRadius.vertical(
            top: Radius.circular(20),
          ),
          border: Border.all(
            color: ResponsiveHelper.backgroundTertiary,
            width: 1,
          ),
        ),
        child: Column(
          children: [
            // Handle bar
            Container(
              margin: const EdgeInsets.only(top: 8),
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: ResponsiveHelper.textQuaternary,
                borderRadius: BorderRadius.circular(2),
              ),
            ),

            // Header
            Padding(
              padding: const EdgeInsets.all(20),
              child: Row(
                children: [
                  const Icon(
                    FontAwesomeIcons.dollarSign,
                    color: ResponsiveHelper.textSecondary,
                    size: 18,
                  ),
                  const SizedBox(width: 12),
                  Text(
                    context.l10n.appPricingLabel,
                    style: const TextStyle(
                      color: ResponsiveHelper.textPrimary,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),

            // Pricing options
            Expanded(
              child: ListView.separated(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                separatorBuilder: (context, index) => Container(
                  height: 1,
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                ),
                itemCount: options.length,
                itemBuilder: (context, index) {
                  final option = options[index];
                  final provider = context.watch<AddAppProvider>();
                  final isSelected = (option == context.l10n.pricingPaid && provider.isPaid) || (option == context.l10n.pricingFree && !provider.isPaid);

                  return Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () {
                        provider.setIsPaid(option == context.l10n.pricingPaid);
                        Navigator.pop(context);
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                option,
                                style: const TextStyle(
                                  color: ResponsiveHelper.textPrimary,
                                  fontSize: 16,
                                ),
                              ),
                            ),
                            if (isSelected)
                              const Icon(
                                FontAwesomeIcons.check,
                                color: ResponsiveHelper.purplePrimary,
                                size: 16,
                              ),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
