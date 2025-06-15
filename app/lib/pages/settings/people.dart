import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/functions.dart';
import 'package:just_audio/just_audio.dart';
import 'package:provider/provider.dart';

class UserPeoplePage extends StatelessWidget {
  const UserPeoplePage({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (context) => PeopleProvider(),
      child: const _UserPeoplePage(),
    );
  }
}

class _UserPeoplePage extends StatefulWidget {
  const _UserPeoplePage();

  @override
  State<_UserPeoplePage> createState() => _UserPeoplePageState();
}

class _UserPeoplePageState extends State<_UserPeoplePage> {
  @override
  void initState() {
    super.initState();
    () {
      context.read<PeopleProvider>().initialize();
    }.withPostFrameCallback();
  }

  Widget _showPersonDialogForm(formKey, nameController) {
    return Platform.isIOS
        ? Material(
            color: Colors.transparent,
            child: Theme(
              data: ThemeData(
                textSelectionTheme: const TextSelectionThemeData(
                  cursorColor: Colors.white,
                  selectionColor: Colors.white24,
                  selectionHandleColor: Colors.white,
                ),
              ),
              child: Form(
                key: formKey,
                child: CupertinoTextFormFieldRow(
                  padding: const EdgeInsets.only(top: 16),
                  controller: nameController,
                  placeholder: 'Name',
                  keyboardType: TextInputType.name,
                  textCapitalization: TextCapitalization.words,
                  placeholderStyle: const TextStyle(color: Colors.white),
                  style: const TextStyle(color: Colors.white),
                  validator: _nameValidator,
                ),
              ),
            ),
          )
        : Form(
            key: formKey,
            child: TextFormField(
              controller: nameController,
              keyboardType: TextInputType.name,
              textCapitalization: TextCapitalization.words,
              decoration: InputDecoration(
                labelText: 'Name',
                labelStyle: const TextStyle(color: Colors.white),
                focusColor: Colors.white,
                focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: Colors.grey.shade300)),
              ),
              validator: _nameValidator,
            ),
          );
  }

  String? _nameValidator(String? value) {
    if (value == null || value.isEmpty) {
      return 'Please enter a name';
    }
    if (value.length < 2 || value.length > 40) {
      return 'Name must be between 2 and 40 characters';
    }
    return null;
  }

  List<Widget> _showPersonDialogActions(
    BuildContext context,
    formKey,
    nameController,
    PeopleProvider provider, {
    Person? person,
  }) {
    onPressed() async {
      if (formKey.currentState!.validate()) {
        provider.addOrUpdatePersonProvider(person, nameController);
        Navigator.pop(context);
      }
    }

    return Platform.isIOS
        ? [
            CupertinoDialogAction(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel', style: TextStyle(color: Colors.white)),
            ),
            CupertinoDialogAction(
              onPressed: onPressed,
              child: Text(person == null ? 'Add' : 'Update', style: const TextStyle(color: Colors.white)),
            ),
          ]
        : [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            TextButton(
              onPressed: onPressed,
              child: Text(person == null ? 'Add' : 'Update', style: const TextStyle(color: Colors.white)),
            ),
          ];
  }

  Future<void> _showPersonDialog(BuildContext context, PeopleProvider provider, {Person? person}) async {
    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
    if (!connectivityProvider.isConnected) {
      ConnectivityProvider.showNoInternetDialog(context);
      return;
    }

    final nameController = TextEditingController(text: person?.name ?? '');
    final formKey = GlobalKey<FormState>();

    await showDialog(
      context: context,
      builder: (BuildContext context) => Platform.isIOS
          ? CupertinoAlertDialog(
              title: Text(person == null ? 'Add New Person' : 'Edit Person'),
              content: _showPersonDialogForm(formKey, nameController),
              actions: _showPersonDialogActions(context, formKey, nameController, provider, person: person),
            )
          : AlertDialog(
              title: Text(person == null ? 'Add New Person' : 'Edit Person'),
              content: _showPersonDialogForm(formKey, nameController),
              actions: _showPersonDialogActions(context, formKey, nameController, provider, person: person),
            ),
    );
  }

  Future<void> _confirmDeleteSample(int peopleIdx, Person person, String url, PeopleProvider provider) async {
    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
    if (!connectivityProvider.isConnected) {
      ConnectivityProvider.showNoInternetDialog(context);
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (c) => getDialog(
        context,
        () => Navigator.pop(context, false),
        () => Navigator.pop(context, true),
        'Delete Sample?',
        'Are you sure you want to delete ${person.name}\'s sample?',
        okButtonText: 'Confirm',
      ),
    );

    if (confirmed == true) {
      provider.deletePersonSample(peopleIdx, url);
    }
  }

  Future<void> _confirmDeletePerson(Person person, PeopleProvider provider) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (c) => getDialog(
        context,
        () => Navigator.pop(context, false),
        () => Navigator.pop(context, true),
        'Confirm Deletion',
        'Are you sure you want to delete ${person.name}? This will also remove all associated speech samples.',
        okButtonText: 'Confirm',
      ),
    );

    if (confirmed == true) provider.deletePersonProvider(person);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PeopleProvider>(
      builder: (context, provider, child) {
        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            title: const Text('People'),
            backgroundColor: Theme.of(context).colorScheme.primary,
            centerTitle: true,
            actions: [
              IconButton(
                icon: const Icon(Icons.add),
                onPressed: () => _showPersonDialog(context, provider),
              ),
              provider.people.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.question_mark),
                      onPressed: () {
                        showDialog(
                          context: context,
                          builder: (c) => getDialog(
                            context,
                            () => Navigator.pop(context),
                            () => Navigator.pop(context),
                            singleButton: true,
                            'How it works?',
                            'Once a person is created, you can go to a conversation transcript, and assign them their corresponding segments, that way Omi will be able to recognize their speech too!',
                            okButtonText: 'Got it',
                          ),
                        );
                      })
                  : const SizedBox(),
            ],
          ),
          body: provider.loading
              ? const Center(
                  child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                )
              : provider.people.isEmpty
                  ? const Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Icon(Icons.question_mark, size: 40),
                          SizedBox(height: 24),
                          Padding(
                            padding: EdgeInsets.symmetric(horizontal: 32),
                            child: Text('Create a new person and train Omi to recognize their speech too!',
                                style: TextStyle(color: Colors.white, fontSize: 24), textAlign: TextAlign.center),
                          ),
                          SizedBox(height: 64),
                        ],
                      ),
                    )
                  : ListView.separated(
                      itemCount: provider.people.length,
                      separatorBuilder: (context, index) => const Divider(height: 1),
                      itemBuilder: (context, index) {
                        final person = provider.people[index];
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            ListTile(
                              title: Text(
                                person.name,
                                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w500),
                              ),
                              onTap: () => _showPersonDialog(context, provider, person: person),
                              trailing: IconButton(
                                icon: const Icon(Icons.delete, size: 20),
                                onPressed: () => _confirmDeletePerson(person, provider),
                              ),
                            ),
                            if (person.speechSamples != null && person.speechSamples!.isNotEmpty)
                              Padding(
                                padding: const EdgeInsets.only(left: 8, right: 16, bottom: 8),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const SizedBox(height: 4),
                                    ...person.speechSamples!.mapIndexed((j, sample) => ListTile(
                                          contentPadding: EdgeInsets.zero,
                                          leading: IconButton(
                                            padding: const EdgeInsets.all(0),
                                            icon: Icon(
                                              provider.currentPlayingPersonIndex == index &&
                                                      provider.currentPlayingIndex == j &&
                                                      provider.isPlaying
                                                  ? Icons.pause
                                                  : Icons.play_arrow,
                                            ),
                                            onPressed: () => provider.playPause(index, j, sample),
                                          ),
                                          title: Text(index == 0 ? 'Speech Profile' : 'Sample $index'),
                                          onTap: () => _confirmDeleteSample(index, person, sample, provider),
                                          subtitle: FutureBuilder<Duration?>(
                                            future: AudioPlayer().setUrl(sample),
                                            builder: (context, snapshot) {
                                              if (snapshot.hasData) {
                                                return Text('${snapshot.data!.inSeconds} seconds');
                                              } else {
                                                return const Text('Loading duration...');
                                              }
                                            },
                                          ),
                                        )),
                                  ],
                                ),
                              ),
                          ],
                        );
                      },
                    ),
        );
      },
    );
  }
}
