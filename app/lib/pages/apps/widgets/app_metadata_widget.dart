import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:provider/provider.dart';

class AppMetadataWidget extends StatelessWidget {
  final File? imageFile;
  final String? imageUrl;
  final VoidCallback pickImage;
  final TextEditingController appNameController;
  final TextEditingController appDescriptionController;
  final TextEditingController creatorNameController;
  final TextEditingController creatorEmailController;
  final List<Category> categories;
  final Function(String?) setAppCategory;
  final String? category;

  const AppMetadataWidget({
    super.key,
    this.imageFile,
    this.imageUrl,
    required this.pickImage,
    required this.appNameController,
    required this.appDescriptionController,
    required this.creatorNameController,
    required this.creatorEmailController,
    required this.categories,
    required this.setAppCategory,
    this.category,
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
                      border: Border.all(color: Colors.grey.shade800, width: 2.0),
                    ),
                    child: imageFile != null || imageUrl != null
                        ? (imageUrl == null
                            ? ClipRRect(
                                borderRadius: BorderRadius.circular(30.0),
                                child: Image.file(imageFile!, fit: BoxFit.cover))
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
                              color: Colors.grey.shade800,
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
                color: Colors.grey.shade900,
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
                      color: Colors.grey.shade800,
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
                        color: Colors.grey.shade800,
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
                            style: TextStyle(
                                color: category != null ? Colors.grey.shade100 : Colors.grey.shade400, fontSize: 16),
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
                      'Creator Name',
                      style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
                    margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade800,
                      borderRadius: BorderRadius.circular(10.0),
                    ),
                    width: double.infinity,
                    child: TextFormField(
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return 'Please enter creator name';
                        }
                        return null;
                      },
                      controller: creatorNameController,
                      decoration: const InputDecoration(
                        contentPadding: EdgeInsets.only(top: 6, bottom: 6),
                        isDense: true,
                        errorText: null,
                        border: InputBorder.none,
                        hintText: 'Nik Shevchenko',
                      ),
                    ),
                  ),
                  const SizedBox(
                    height: 16,
                  ),
                  Padding(
                    padding: const EdgeInsets.only(left: 8.0),
                    child: Text(
                      'Email Address',
                      style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
                    margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade800,
                      borderRadius: BorderRadius.circular(10.0),
                    ),
                    width: double.infinity,
                    child: TextFormField(
                      controller: creatorEmailController,
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return 'Please enter creator email';
                        }
                        return null;
                      },
                      decoration: const InputDecoration(
                        contentPadding: EdgeInsets.only(top: 6, bottom: 6),
                        isDense: true,
                        border: InputBorder.none,
                        hintText: 'nik@basedhardware.com',
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
                      color: Colors.grey.shade800,
                      borderRadius: BorderRadius.circular(10.0),
                    ),
                    width: double.infinity,
                    child: ConstrainedBox(
                      constraints: BoxConstraints(
                        minHeight: MediaQuery.sizeOf(context).height * 0.1,
                        maxHeight: MediaQuery.sizeOf(context).height * 0.4,
                      ),
                      child: Scrollbar(
                        child: SingleChildScrollView(
                          scrollDirection: Axis.vertical,
                          reverse: false,
                          child: TextFormField(
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
                              hintText:
                                  'My Awesome App is a great app that does amazing things. It is the best app ever!',
                              hintMaxLines: 4,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
