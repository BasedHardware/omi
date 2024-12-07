import 'package:flutter/material.dart';
import 'package:friend_private/pages/settings/creator_profile/creator_profile_provider.dart';
import 'package:friend_private/utils/other/text_formatters.dart';
import 'package:friend_private/utils/other/validators.dart';
import 'package:provider/provider.dart';

class CreatorProfileWrapper extends StatelessWidget {
  const CreatorProfileWrapper({super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableProvider(
      create: (_) => CreatorProfileProvider()..getCreatorProfileDetails(),
      builder: (context, child) {
        return const CreatorProfile();
      },
    );
  }
}

class CreatorProfile extends StatelessWidget {
  const CreatorProfile({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<CreatorProfileProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.primary,
          elevation: 0,
          title: const Text('Creator Profile'),
          centerTitle: false,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new),
            onPressed: () {
              Navigator.pop(context);
            },
          ),
        ),
        body: provider.isLoading
            ? const Center(
                child: CircularProgressIndicator(
                  color: Colors.white,
                ),
              )
            : SingleChildScrollView(
                child: Form(
                  key: provider.formKey,
                  onChanged: () {
                    provider.submitButtonStatus();
                  },
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Column(
                      children: [
                        Container(
                          decoration: BoxDecoration(
                            color: Colors.grey.shade900,
                            borderRadius: BorderRadius.circular(12.0),
                          ),
                          padding: const EdgeInsets.all(14.0),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const SizedBox(
                                height: 6,
                              ),
                              Padding(
                                padding: const EdgeInsets.only(left: 8.0),
                                child: Text(
                                  'Creator Name',
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
                                  controller: provider.creatorNameController,
                                  validator: (value) {
                                    if (value == null || value.isEmpty) {
                                      return 'Please provide a valid name';
                                    }
                                    return null;
                                  },
                                  decoration: const InputDecoration(
                                    error: null,
                                    errorText: null,
                                    isDense: true,
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
                                  'Creator Email',
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
                                  controller: provider.creatorEmailController,
                                  inputFormatters: [
                                    LowercaseTextInputFormatter(),
                                  ],
                                  validator: (value) {
                                    if (value == null || !isValidEmail(value)) {
                                      return 'Please provide a valid Email Address for communication';
                                    }
                                    return null;
                                  },
                                  decoration: const InputDecoration(
                                    errorText: null,
                                    error: null,
                                    isDense: true,
                                    border: InputBorder.none,
                                    hintText: 'Nik@basedhardware.com',
                                  ),
                                ),
                              ),
                              const SizedBox(
                                height: 2,
                              ),
                              Row(
                                children: [
                                  const SizedBox(
                                    width: 8,
                                  ),
                                  Icon(
                                    Icons.info_outline,
                                    color: Colors.grey.shade400,
                                    size: 16,
                                  ),
                                  const SizedBox(
                                    width: 8,
                                  ),
                                  SizedBox(
                                    width: MediaQuery.sizeOf(context).width * 0.76,
                                    child: Text(
                                      'This email will be public and used for communication.',
                                      style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
                                    ),
                                  ),
                                ],
                              )
                            ],
                          ),
                        ),
                        const SizedBox(
                          height: 16,
                        ),
                        Container(
                          decoration: BoxDecoration(
                            color: Colors.grey.shade900,
                            borderRadius: BorderRadius.circular(12.0),
                          ),
                          padding: const EdgeInsets.all(14.0),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const SizedBox(
                                height: 6,
                              ),
                              Padding(
                                padding: const EdgeInsets.only(left: 8.0),
                                child: Text(
                                  'PayPal Email',
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
                                  controller: provider.paypalEmailController,
                                  inputFormatters: [
                                    LowercaseTextInputFormatter(),
                                  ],
                                  validator: (value) {
                                    if (value == null || !isValidEmail(value)) {
                                      return 'Please provide a valid PayPal Email';
                                    }
                                    return null;
                                  },
                                  decoration: const InputDecoration(
                                    errorText: null,
                                    isDense: true,
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
                                  'PayPal.Me Link',
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
                                  inputFormatters: [
                                    LowercaseTextInputFormatter(),
                                  ],
                                  controller: provider.paypalMeLinkController,
                                  validator: (value) {
                                    if (value == null || !isValidPayPalMeLink(value)) {
                                      return 'Please provide a valid PayPal.Me Link';
                                    }
                                    return null;
                                  },
                                  decoration: const InputDecoration(
                                    errorText: null,
                                    isDense: true,
                                    border: InputBorder.none,
                                    hintText: 'paypal.me/nikshevchenko',
                                  ),
                                ),
                              ),
                            ],
                          ),
                        )
                      ],
                    ),
                  ),
                ),
              ),
        bottomNavigationBar: provider.isLoading
            ? null
            : Container(
                padding: const EdgeInsets.only(left: 30.0, right: 30, bottom: 50, top: 10),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12.0),
                  color: Colors.grey.shade900,
                  gradient: LinearGradient(
                    colors: [Colors.black, Colors.black.withOpacity(0)],
                    begin: Alignment.bottomCenter,
                    end: Alignment.topCenter,
                  ),
                ),
                child: GestureDetector(
                  onTap: provider.showSubmitButton
                      ? () async {
                          if (provider.profileExists) {
                            await provider.updateDetails();
                          } else {
                            await provider.saveDetails();
                          }
                        }
                      : null,
                  child: Container(
                    padding: const EdgeInsets.all(12.0),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(12.0),
                      color: provider.showSubmitButton ? Colors.white : Colors.grey.shade700,
                    ),
                    child: const Text(
                      'Save Details',
                      style: TextStyle(color: Colors.black, fontSize: 16),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              ),
      );
    });
  }
}
