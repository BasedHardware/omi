import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:dotted_border/dotted_border.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';

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
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'App Metadata',
          style: TextStyle(color: Colors.white, fontSize: 16),
        ),
        const SizedBox(
          height: 16,
        ),
        GestureDetector(
          onTap: pickImage,
          child: imageFile != null || imageUrl != null
              ? (imageUrl == null
                  ? Container(
                      height: 100,
                      width: double.infinity,
                      decoration: BoxDecoration(
                        border: Border.all(color: Colors.grey[500] ?? Colors.grey),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        mainAxisAlignment: MainAxisAlignment.start,
                        children: [
                          const SizedBox(
                            width: 30,
                          ),
                          ClipRRect(
                            borderRadius: BorderRadius.circular(8.0),
                            child: Image.file(
                              imageFile!,
                              height: 60,
                              width: 60,
                              fit: BoxFit.cover,
                            ),
                          ),
                          const SizedBox(
                            width: 30,
                          ),
                          const Text(
                            'Replace App Icon?',
                            style: TextStyle(color: Colors.white, fontSize: 16),
                          ),
                        ],
                      ),
                    )
                  : CachedNetworkImage(
                      imageUrl: imageUrl!,
                      imageBuilder: (context, imageProvider) => Container(
                        height: 100,
                        width: double.infinity,
                        decoration: BoxDecoration(
                          border: Border.all(color: Colors.grey[500] ?? Colors.grey),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          mainAxisAlignment: MainAxisAlignment.start,
                          children: [
                            const SizedBox(
                              width: 30,
                            ),
                            ClipRRect(
                              borderRadius: BorderRadius.circular(8.0),
                              child: Image(image: imageProvider, height: 60, width: 60, fit: BoxFit.cover),
                            ),
                            const SizedBox(
                              width: 30,
                            ),
                            const Text(
                              'Replace App Icon?',
                              style: TextStyle(color: Colors.white, fontSize: 16),
                            ),
                          ],
                        ),
                      ),
                    ))
              : DottedBorder(
                  borderType: BorderType.RRect,
                  dashPattern: [6, 3],
                  radius: const Radius.circular(10),
                  color: Colors.grey[600] ?? Colors.grey,
                  child: Container(
                    height: 100,
                    width: double.infinity,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(10),
                      color: Colors.transparent,
                    ),
                    child: Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.cloud_upload,
                            color: Colors.grey,
                            size: 32,
                          ),
                          SizedBox(
                            height: 8,
                          ),
                          Text(
                            '${imageUrl == null ? 'Upload' : 'Replace'} App Icon',
                            style: TextStyle(color: Colors.grey),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
        ),
        const SizedBox(
          height: 20,
        ),
        TextFormField(
          controller: appNameController,
          validator: (value) {
            if (value == null || value.isEmpty) {
              return 'Please enter app name';
            }
            return null;
          },
          decoration: InputDecoration(
            border: const OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(10)),
            ),
            focusedBorder: const OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(10)),
              borderSide: BorderSide(
                color: Colors.white,
              ),
            ),
            label: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.apps,
                    color: WidgetStateColor.resolveWith(
                        (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                const SizedBox(
                  width: 8,
                ),
                const Text(
                  'App Name',
                ),
              ],
            ),
            alignLabelWithHint: true,
            labelStyle: const TextStyle(
              color: Colors.grey,
            ),
            floatingLabelStyle: const TextStyle(
              color: Colors.white,
            ),
          ),
        ),
        const SizedBox(
          height: 24,
        ),
        DropdownButtonFormField(
          validator: (value) {
            if (value == null) {
              return 'Please select an app category';
            }
            return null;
          },
          value: category,
          decoration: InputDecoration(
            border: const OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(10)),
            ),
            focusedBorder: const OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(10)),
              borderSide: BorderSide(
                color: Colors.white,
              ),
            ),
            label: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.category,
                    color: WidgetStateColor.resolveWith(
                        (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                const SizedBox(
                  width: 8,
                ),
                const Text(
                  'App Category',
                ),
              ],
            ),
            labelStyle: const TextStyle(
              color: Colors.grey,
            ),
            floatingLabelStyle: const TextStyle(
              color: Colors.white,
            ),
          ),
          items: categories
              .map(
                (category) => DropdownMenuItem(
                  value: category.id,
                  child: Text(category.title),
                ),
              )
              .toList(),
          onChanged: setAppCategory,
        ),
        const SizedBox(
          height: 24,
        ),
        TextFormField(
          validator: (value) {
            if (value == null || value.isEmpty) {
              return 'Please enter creator name';
            }
            return null;
          },
          controller: creatorNameController,
          decoration: InputDecoration(
            border: const OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(10)),
            ),
            focusedBorder: const OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(10)),
              borderSide: BorderSide(
                color: Colors.white,
              ),
            ),
            label: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.person,
                    color: WidgetStateColor.resolveWith(
                        (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                const SizedBox(
                  width: 8,
                ),
                const Text(
                  'Creator Name',
                ),
              ],
            ),
            alignLabelWithHint: true,
            labelStyle: const TextStyle(
              color: Colors.grey,
            ),
            floatingLabelStyle: const TextStyle(
              color: Colors.white,
            ),
          ),
        ),
        const SizedBox(
          height: 24,
        ),
        TextFormField(
          validator: (value) {
            if (value == null || value.isEmpty) {
              return 'Please enter creator email';
            }
            return null;
          },
          controller: creatorEmailController,
          decoration: InputDecoration(
            border: const OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(10)),
            ),
            focusedBorder: const OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(10)),
              borderSide: BorderSide(
                color: Colors.white,
              ),
            ),
            label: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.email,
                    color: WidgetStateColor.resolveWith(
                        (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                const SizedBox(
                  width: 8,
                ),
                const Text(
                  'Email Address',
                ),
              ],
            ),
            alignLabelWithHint: true,
            labelStyle: const TextStyle(
              color: Colors.grey,
            ),
            floatingLabelStyle: const TextStyle(
              color: Colors.white,
            ),
          ),
        ),
        const SizedBox(
          height: 24,
        ),
        TextFormField(
          maxLines: null,
          validator: (value) {
            if (value == null || value.isEmpty) {
              return 'Please provide a valid description';
            }
            return null;
          },
          controller: appDescriptionController,
          decoration: InputDecoration(
            border: const OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(10)),
            ),
            focusedBorder: const OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(10)),
              borderSide: BorderSide(
                color: Colors.white,
              ),
            ),
            label: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.description,
                    color: WidgetStateColor.resolveWith(
                        (states) => states.contains(WidgetState.focused) ? Colors.white : Colors.grey)),
                const SizedBox(
                  width: 8,
                ),
                const Text(
                  'Description',
                ),
              ],
            ),
            alignLabelWithHint: true,
            labelStyle: const TextStyle(
              color: Colors.grey,
            ),
            floatingLabelStyle: const TextStyle(
              color: Colors.white,
            ),
          ),
        ),
      ],
    );
  }
}
