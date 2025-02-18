import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/persona/persona_provider.dart';
import 'package:friend_private/utils/other/debouncer.dart';
import 'package:friend_private/utils/text_formatter.dart';
import 'package:friend_private/widgets/animated_loading_button.dart';
import 'package:provider/provider.dart';

class UpdatePersonaPage extends StatefulWidget {
  final App app;
  const UpdatePersonaPage({super.key, required this.app});

  @override
  State<UpdatePersonaPage> createState() => _UpdatePersonaPageState();
}

class _UpdatePersonaPageState extends State<UpdatePersonaPage> {
  final _debouncer = Debouncer(delay: const Duration(milliseconds: 500));

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<PersonaProvider>().prepareUpdatePersona(widget.app);
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PersonaProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Colors.black,
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          title: const Text('Create Persona', style: TextStyle(color: Colors.white)),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back, color: Colors.white),
            onPressed: () => Navigator.pop(context),
          ),
        ),
        body: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.all(24.0),
            child: Form(
              key: provider.formKey,
              onChanged: () {
                provider.validateForm();
              },
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Center(
                    child: GestureDetector(
                      onTap: () async {
                        await provider.pickImage();
                      },
                      child: Container(
                        width: 120,
                        height: 120,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade900,
                          borderRadius: BorderRadius.circular(60),
                          border: Border.all(color: Colors.grey.shade800),
                        ),
                        // child: provider.selectedImage != null
                        //     ? ClipRRect(
                        //         borderRadius: BorderRadius.circular(60),
                        //         child: Image.file(
                        //           provider.selectedImage!,
                        //           fit: BoxFit.cover,
                        //         ),
                        //       )
                        //     : Icon(
                        //         Icons.add_a_photo,
                        //         size: 40,
                        //         color: Colors.grey.shade400,
                        //       ),
                        child: provider.selectedImage != null || provider.selectedImageUrl != null
                            ? (provider.selectedImageUrl == null
                                ? ClipRRect(
                                    borderRadius: BorderRadius.circular(60),
                                    child: Image.file(provider.selectedImage!, fit: BoxFit.cover))
                                : ClipRRect(
                                    borderRadius: BorderRadius.circular(60),
                                    child: CachedNetworkImage(imageUrl: provider.selectedImageUrl!),
                                  ))
                            : const Icon(Icons.add_a_photo, color: Colors.grey, size: 32),
                      ),
                    ),
                  ),
                  const SizedBox(height: 32),
                  Container(
                    decoration: BoxDecoration(
                      color: Colors.grey.shade900,
                      borderRadius: BorderRadius.circular(12.0),
                    ),
                    padding: const EdgeInsets.all(14.0),
                    margin: const EdgeInsets.only(top: 22),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(left: 8.0),
                          child: Text(
                            'Persona Name',
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
                                return 'Please enter a username to access the persona';
                              }
                              return null;
                            },
                            controller: provider.nameController,
                            decoration: const InputDecoration(
                              isDense: true,
                              border: InputBorder.none,
                              hintText: 'Nik AI',
                            ),
                          ),
                        ),
                        const SizedBox(
                          height: 24,
                        ),
                        Padding(
                          padding: const EdgeInsets.only(left: 8.0),
                          child: Text(
                            'Persona Username',
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
                                return 'Please enter a username to access the persona';
                              }
                              return null;
                            },
                            onChanged: (value) {
                              _debouncer.run(() async {
                                await provider.checkIsUsernameTaken(value);
                              });
                            },
                            controller: provider.usernameController,
                            inputFormatters: [
                              LowerCaseTextFormatter(),
                              FilteringTextInputFormatter.allow(RegExp(r'[a-z0-9_]')),
                            ],
                            decoration: InputDecoration(
                              isDense: true,
                              border: InputBorder.none,
                              hintText: 'nikshevchenko',
                              suffix: provider.usernameController.text.isEmpty
                                  ? null
                                  : provider.isCheckingUsername
                                      ? const SizedBox(
                                          width: 16,
                                          height: 16,
                                          child: Center(
                                            child: CircularProgressIndicator(
                                              strokeWidth: 2,
                                              valueColor: AlwaysStoppedAnimation<Color>(Colors.grey),
                                            ),
                                          ),
                                        )
                                      : Icon(
                                          provider.isUsernameTaken ? Icons.close : Icons.check,
                                          color: provider.isUsernameTaken ? Colors.red : Colors.green,
                                          size: 16,
                                        ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 22),
                  Container(
                    padding: const EdgeInsets.only(left: 14.0),
                    child: Row(
                      children: [
                        Text(
                          'Make Persona Public',
                          style: TextStyle(color: Colors.grey.shade400),
                        ),
                        const Spacer(),
                        Switch(
                          value: provider.makePersonaPublic,
                          onChanged: (value) {
                            provider.setPersonaPublic(value);
                          },
                          activeColor: Colors.white,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        bottomNavigationBar: Padding(
          padding: const EdgeInsets.only(left: 24, right: 24, bottom: 52),
          child: SizedBox(
            width: double.infinity,
            child: AnimatedLoadingButton(
              onPressed: !provider.isFormValid
                  ? () async {}
                  : () async {
                      await provider.createPersona();
                    },
              color: provider.isFormValid ? Colors.white : Colors.grey[800]!,
              loaderColor: Colors.black,
              text: "Create Persona",
              textStyle: const TextStyle(
                color: Colors.black,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
      );
    });
  }
}
