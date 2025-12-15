import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/svg.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:provider/provider.dart';
import 'package:skeletonizer/skeletonizer.dart';

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
          children: [
            Container(
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25),
                borderRadius: BorderRadius.circular(18.0),
              ),
              padding: const EdgeInsets.all(14.0),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // App ID field with copy button (only shown when updating)
                  context.watch<AddAppProvider>().updateAppId != null
                      ? Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Padding(
                              padding: const EdgeInsets.only(left: 8.0),
                              child: Text(
                                'App ID',
                                style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                              ),
                            ),
                            Container(
                              margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                              padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 10.0),
                              decoration: BoxDecoration(
                                color: Colors.transparent,
                                borderRadius: BorderRadius.circular(12.0),
                                border: Border.all(color: Colors.grey.withOpacity(0.3), width: 1),
                              ),
                              width: double.infinity,
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      context.watch<AddAppProvider>().updateAppId!,
                                      style: TextStyle(color: Colors.grey.shade500, fontSize: 16),
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                  GestureDetector(
                                    onTap: () {
                                      Clipboard.setData(
                                          ClipboardData(text: context.read<AddAppProvider>().updateAppId!));
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        const SnackBar(
                                          content: Text('App ID copied to clipboard'),
                                          duration: Duration(seconds: 2),
                                        ),
                                      );
                                    },
                                    child: Container(
                                      padding: const EdgeInsets.all(6.0),
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(8.0),
                                      ),
                                      child: FaIcon(
                                        FontAwesomeIcons.copy,
                                        color: Colors.white,
                                        size: 16,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 16),
                          ],
                        )
                      : const SizedBox.shrink(),
                  // Row with Image picker on left, Name and Category on right
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Image picker
                      Stack(
                        children: [
                          GestureDetector(
                            onTap: pickImage,
                            child: Container(
                              width: 110,
                              height: 105,
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(16.0),
                                border: Border.all(color: const Color(0xFF35343B), width: 2.0),
                              ),
                              child: imageFile != null || imageUrl != null
                                  ? (imageUrl == null
                                      ? ClipRRect(
                                          borderRadius: BorderRadius.circular(14.0),
                                          child: Image.file(imageFile!, fit: BoxFit.cover))
                                      : ClipRRect(
                                          borderRadius: BorderRadius.circular(14.0),
                                          child: CachedNetworkImage(imageUrl: imageUrl!, fit: BoxFit.cover),
                                        ))
                                  : const Center(
                                      child: FaIcon(FontAwesomeIcons.camera, color: Colors.grey, size: 24),
                                    ),
                            ),
                          ),
                          if (imageFile != null || imageUrl != null)
                            Positioned(
                              bottom: -4,
                              right: -4,
                              child: GestureDetector(
                                onTap: pickImage,
                                child: Container(
                                  padding: const EdgeInsets.all(6.0),
                                  decoration: const BoxDecoration(
                                    color: Color(0xFF35343B),
                                    shape: BoxShape.circle,
                                  ),
                                  child: const FaIcon(
                                    FontAwesomeIcons.pen,
                                    color: Colors.white,
                                    size: 12,
                                  ),
                                ),
                              ),
                            ),
                        ],
                      ),
                      const SizedBox(width: 14),
                      // Name and Category fields
                      Expanded(
                        child: Column(
                          children: [
                            // App Name field
                            TextFormField(
                              validator: (value) {
                                if (value == null || value.isEmpty) {
                                  return 'Please enter app name';
                                }
                                return null;
                              },
                              controller: appNameController,
                              decoration: InputDecoration(
                                labelText: 'App Name*',
                                labelStyle: TextStyle(color: Colors.grey.shade400),
                                floatingLabelStyle: TextStyle(color: Colors.grey.shade300),
                                contentPadding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 14.0),
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12.0),
                                  borderSide: BorderSide(color: Colors.grey.withOpacity(0.3), width: 1),
                                ),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12.0),
                                  borderSide: BorderSide(color: Colors.grey.withOpacity(0.3), width: 1),
                                ),
                                focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12.0),
                                  borderSide: BorderSide(color: Colors.grey.shade400, width: 1),
                                ),
                                errorBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12.0),
                                  borderSide: BorderSide(color: Colors.red.shade300, width: 1),
                                ),
                                filled: false,
                              ),
                            ),
                            const SizedBox(height: 10),
                            // Category selector
                            GestureDetector(
                              onTap: () {
                                showModalBottomSheet(
                                  context: context,
                                  isScrollControlled: true,
                                  shape: const RoundedRectangleBorder(
                                    borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                                  ),
                                  builder: (context) {
                                    return Consumer<AddAppProvider>(builder: (context, provider, child) {
                                      return Container(
                                        padding: const EdgeInsets.all(16.0),
                                        height: MediaQuery.of(context).size.height * 0.6,
                                        child: SingleChildScrollView(
                                          child: Column(
                                            mainAxisSize: MainAxisSize.min,
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              const SizedBox(height: 12),
                                              const Text(
                                                'App Category',
                                                style: TextStyle(color: Colors.white, fontSize: 18),
                                              ),
                                              const SizedBox(height: 18),
                                              ListView.separated(
                                                separatorBuilder: (context, index) {
                                                  return Divider(
                                                    color: Colors.grey.shade600,
                                                    height: 1,
                                                  );
                                                },
                                                shrinkWrap: true,
                                                itemCount: categories.length,
                                                physics: const NeverScrollableScrollPhysics(),
                                                itemBuilder: (context, index) {
                                                  return InkWell(
                                                    onTap: () {
                                                      provider.setAppCategory(categories[index].id);
                                                      Navigator.pop(context);
                                                    },
                                                    child: Container(
                                                      padding: const EdgeInsets.symmetric(vertical: 10),
                                                      child: Row(
                                                        crossAxisAlignment: CrossAxisAlignment.center,
                                                        children: [
                                                          const SizedBox(width: 6),
                                                          Text(
                                                            categories[index].title,
                                                            style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                                                          ),
                                                          const Spacer(),
                                                          Checkbox(
                                                            value: provider.appCategory == categories[index].id,
                                                            onChanged: (value) {
                                                              provider.setAppCategory(categories[index].id);
                                                              Navigator.pop(context);
                                                            },
                                                            side: BorderSide(color: Colors.grey.shade300),
                                                            shape: const CircleBorder(),
                                                          ),
                                                        ],
                                                      ),
                                                    ),
                                                  );
                                                },
                                              ),
                                            ],
                                          ),
                                        ),
                                      );
                                    });
                                  },
                                );
                              },
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 14.0),
                                decoration: BoxDecoration(
                                  color: Colors.transparent,
                                  borderRadius: BorderRadius.circular(12.0),
                                  border: Border.all(color: Colors.grey.withOpacity(0.3), width: 1),
                                ),
                                width: double.infinity,
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        (category?.isNotEmpty == true ? category : 'Category*') ?? 'Category*',
                                        style: TextStyle(
                                            color: category != null ? Colors.grey.shade100 : Colors.grey.shade400,
                                            fontSize: 16),
                                      ),
                                    ),
                                    FaIcon(
                                      FontAwesomeIcons.chevronRight,
                                      color: Colors.grey.shade400,
                                      size: 14,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  // Description field (full width)
                  Stack(
                    children: [
                      generatingDescription
                          ? Container(
                              padding: const EdgeInsets.all(16.0),
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(12.0),
                                border: Border.all(color: Colors.grey.withOpacity(0.3), width: 1),
                              ),
                              constraints: BoxConstraints(
                                minHeight: MediaQuery.sizeOf(context).height * 0.1,
                              ),
                              child: Skeletonizer.zone(
                                enabled: generatingDescription,
                                effect: ShimmerEffect(
                                  baseColor: Colors.grey[700]!,
                                  highlightColor: Colors.grey[600]!,
                                  duration: const Duration(seconds: 1),
                                ),
                                child: Bone.multiText(),
                              ),
                            )
                          : TextFormField(
                              maxLines: null,
                              minLines: 4,
                              validator: (value) {
                                if (value == null || value.isEmpty) {
                                  return 'Please provide a valid description';
                                }
                                return null;
                              },
                              controller: appDescriptionController,
                              decoration: InputDecoration(
                                labelText: 'Description*',
                                labelStyle: TextStyle(color: Colors.grey.shade400),
                                floatingLabelStyle: TextStyle(color: Colors.grey.shade300),
                                alignLabelWithHint: true,
                                contentPadding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 16.0),
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12.0),
                                  borderSide: BorderSide(color: Colors.grey.withOpacity(0.3), width: 1),
                                ),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12.0),
                                  borderSide: BorderSide(color: Colors.grey.withOpacity(0.3), width: 1),
                                ),
                                focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12.0),
                                  borderSide: BorderSide(color: Colors.grey.shade400, width: 1),
                                ),
                                errorBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12.0),
                                  borderSide: BorderSide(color: Colors.red.shade300, width: 1),
                                ),
                                filled: false,
                              ),
                            ),
                      if (appDescriptionController.text.isNotEmpty && appNameController.text.isNotEmpty)
                        Positioned(
                          bottom: 12,
                          right: 12,
                          child: GestureDetector(
                            onTap: () async {
                              await context.read<AddAppProvider>().generateDescription();
                            },
                            child: SvgPicture.asset(
                              Assets.images.aiMagic,
                              color: Colors.white,
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  allowPaidApps
                      ? GestureDetector(
                          onTap: () {
                            showModalBottomSheet(
                              context: context,
                              isScrollControlled: true,
                              shape: const RoundedRectangleBorder(
                                borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                              ),
                              builder: (context) {
                                return Consumer<AddAppProvider>(builder: (context, provider, child) {
                                  return Container(
                                    padding: const EdgeInsets.all(16.0),
                                    height: MediaQuery.of(context).size.height * 0.36,
                                    child: SingleChildScrollView(
                                      child: Column(
                                        mainAxisSize: MainAxisSize.min,
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          const SizedBox(
                                            height: 12,
                                          ),
                                          const Text(
                                            'App Pricing',
                                            style: TextStyle(color: Colors.white, fontSize: 18),
                                          ),
                                          const SizedBox(
                                            height: 18,
                                          ),
                                          ListView(
                                            shrinkWrap: true,
                                            children: ['Free', 'Paid'].map((e) {
                                              return InkWell(
                                                onTap: () {
                                                  provider.setIsPaid(e == 'Paid');
                                                  Navigator.pop(context);
                                                },
                                                child: Container(
                                                  padding: const EdgeInsets.symmetric(vertical: 10),
                                                  child: Row(
                                                    crossAxisAlignment: CrossAxisAlignment.center,
                                                    children: [
                                                      const SizedBox(
                                                        width: 6,
                                                      ),
                                                      Text(
                                                        e,
                                                        style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                                                      ),
                                                      const Spacer(),
                                                      Checkbox(
                                                        value: provider.isPaid == (e == 'Paid'),
                                                        onChanged: (value) {
                                                          provider.setIsPaid(e == 'Paid');
                                                          Navigator.pop(context);
                                                        },
                                                        side: BorderSide(color: Colors.grey.shade300),
                                                        shape: const CircleBorder(),
                                                      ),
                                                    ],
                                                  ),
                                                ),
                                              );
                                            }).toList(),
                                          ),
                                        ],
                                      ),
                                    ),
                                  );
                                });
                              },
                            );
                          },
                          child: Container(
                            margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                            padding: const EdgeInsets.symmetric(horizontal: 2.0, vertical: 10.0),
                            decoration: BoxDecoration(
                              color: Color(0xFF35343B),
                              borderRadius: BorderRadius.circular(10.0),
                            ),
                            width: double.infinity,
                            child: Row(
                              children: [
                                const SizedBox(
                                  width: 12,
                                ),
                                Text(
                                  (appPricing?.isNotEmpty == true ? appPricing : 'None Selected') ?? 'None Selected',
                                  style: TextStyle(
                                      color: appPricing != null ? Colors.grey.shade100 : Colors.grey.shade400,
                                      fontSize: 16),
                                ),
                                const Spacer(),
                                FaIcon(
                                  FontAwesomeIcons.chevronRight,
                                  color: Colors.grey.shade400,
                                  size: 14,
                                ),
                                const SizedBox(
                                  width: 12,
                                ),
                              ],
                            ),
                          ),
                        )
                      : SizedBox.shrink(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
