import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/svg.dart';
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
            Stack(
              children: [
                GestureDetector(
                  onTap: pickImage,
                  child: Container(
                    margin: const EdgeInsets.all(8.0),
                    width: MediaQuery.of(context).size.width * 0.28,
                    height: MediaQuery.of(context).size.width * 0.28,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(30.0),
                      border: Border.all(color: Color(0xFF35343B), width: 2.0),
                    ),
                    child: imageFile != null || imageUrl != null
                        ? (imageUrl == null
                            ? ClipRRect(borderRadius: BorderRadius.circular(30.0), child: Image.file(imageFile!, fit: BoxFit.cover))
                            : ClipRRect(
                                borderRadius: BorderRadius.circular(30.0),
                                child: CachedNetworkImage(imageUrl: imageUrl!),
                              ))
                        : const Icon(Icons.add_a_photo, color: Colors.grey, size: 32),
                  ),
                ),
                (imageFile != null || imageUrl != null)
                    ? Positioned(
                        bottom: 0,
                        right: 0,
                        child: GestureDetector(
                          onTap: pickImage,
                          child: Container(
                            padding: const EdgeInsets.all(8.0),
                            decoration: BoxDecoration(
                              color: Color(0xFF35343B),
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(
                              Icons.edit,
                              color: Colors.white,
                            ),
                          ),
                        ),
                      )
                    : const SizedBox.shrink(),
              ],
            ),
            const SizedBox(
              height: 18,
            ),
            Container(
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25),
                borderRadius: BorderRadius.circular(12.0),
              ),
              padding: const EdgeInsets.all(14.0),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(
                    height: 10,
                  ),
                  // App ID field with copy button
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
                                color: Color(0xFF35343B),
                                borderRadius: BorderRadius.circular(10.0),
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
                                      Clipboard.setData(ClipboardData(text: context.read<AddAppProvider>().updateAppId!));
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
                                      child: Icon(
                                        Icons.copy,
                                        color: Colors.white,
                                        size: 20,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(
                              height: 16,
                            ),
                          ],
                        )
                      : SizedBox.shrink(),
                  Padding(
                    padding: const EdgeInsets.only(left: 8.0),
                    child: Text(
                      'App Name',
                      style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 6.0),
                    margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                    decoration: BoxDecoration(
                      color: Color(0xFF35343B),
                      borderRadius: BorderRadius.circular(10.0),
                    ),
                    width: double.infinity,
                    child: TextFormField(
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return 'Please enter app name';
                        }
                        return null;
                      },
                      controller: appNameController,
                      decoration: const InputDecoration(
                        errorText: null,
                        isDense: true,
                        border: InputBorder.none,
                        hintText: 'My Awesome App',
                      ),
                    ),
                  ),
                  const SizedBox(
                    height: 16,
                  ),
                  Padding(
                    padding: const EdgeInsets.only(left: 8.0),
                    child: Text(
                      'Category',
                      style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                    ),
                  ),
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
                                    const SizedBox(
                                      height: 12,
                                    ),
                                    const Text(
                                      'App Category',
                                      style: TextStyle(color: Colors.white, fontSize: 18),
                                    ),
                                    const SizedBox(
                                      height: 18,
                                    ),
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
                                                const SizedBox(
                                                  width: 6,
                                                ),
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
                            (category?.isNotEmpty == true ? category : 'Select Category') ?? 'Select Category',
                            style: TextStyle(color: category != null ? Colors.grey.shade100 : Colors.grey.shade400, fontSize: 16),
                          ),
                          const Spacer(),
                          Icon(
                            Icons.arrow_forward_ios_rounded,
                            color: Colors.grey.shade400,
                          ),
                          const SizedBox(
                            width: 12,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(
                    height: 16,
                  ),
                  Padding(
                    padding: const EdgeInsets.only(left: 8.0),
                    child: Text(
                      'Description',
                      style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
                    margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                    decoration: BoxDecoration(
                      color: Color(0xFF35343B),
                      borderRadius: BorderRadius.circular(10.0),
                    ),
                    width: double.infinity,
                    child: Stack(
                      children: [
                        ConstrainedBox(
                          constraints: BoxConstraints(
                            minHeight: MediaQuery.sizeOf(context).height * 0.1,
                            maxHeight: MediaQuery.sizeOf(context).height * 0.4,
                          ),
                          child: Scrollbar(
                            child: SingleChildScrollView(
                              scrollDirection: Axis.vertical,
                              reverse: false,
                              child: generatingDescription
                                  ? Skeletonizer.zone(
                                      enabled: generatingDescription,
                                      effect: ShimmerEffect(
                                        baseColor: Colors.grey[700]!,
                                        highlightColor: Colors.grey[600]!,
                                        duration: Duration(seconds: 1),
                                      ),
                                      child: Bone.multiText(),
                                    )
                                  : TextFormField(
                                      maxLines: null,
                                      validator: (value) {
                                        if (value == null || value.isEmpty) {
                                          return 'Please provide a valid description';
                                        }
                                        return null;
                                      },
                                      controller: appDescriptionController,
                                      decoration: const InputDecoration(
                                        contentPadding: EdgeInsets.only(top: 6, bottom: 2),
                                        isDense: true,
                                        border: InputBorder.none,
                                        hintText: 'My Awesome App is a great app that does amazing things. It is the best app ever!',
                                        hintMaxLines: 4,
                                      ),
                                    ),
                            ),
                          ),
                        ),
                        appDescriptionController.text.isNotEmpty && appNameController.text.isNotEmpty
                            ? Positioned(
                                bottom: 2,
                                right: 0,
                                child: GestureDetector(
                                  onTap: () async {
                                    await context.read<AddAppProvider>().generateDescription();
                                  },
                                  child: SvgPicture.asset(
                                    Assets.images.aiMagic,
                                    color: Colors.white,
                                  ),
                                ),
                              )
                            : SizedBox.shrink(),
                      ],
                    ),
                  ),
                  const SizedBox(
                    height: 16,
                  ),
                  allowPaidApps
                      ? Padding(
                          padding: const EdgeInsets.only(left: 8.0),
                          child: Text(
                            'App Pricing',
                            style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                          ),
                        )
                      : SizedBox.shrink(),
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
                                  style: TextStyle(color: appPricing != null ? Colors.grey.shade100 : Colors.grey.shade400, fontSize: 16),
                                ),
                                const Spacer(),
                                Icon(
                                  Icons.arrow_forward_ios_rounded,
                                  color: Colors.grey.shade400,
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
