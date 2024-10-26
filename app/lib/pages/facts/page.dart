import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/fact.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/facts_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/extensions/functions.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

class FactsPage extends StatelessWidget {
  const FactsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => FactsProvider(),
      child: const _FactsPage(),
    );
  }
}

class _FactsPage extends StatefulWidget {
  const _FactsPage();

  @override
  State<_FactsPage> createState() => _FactsPageState();
}

class _FactsPageState extends State<_FactsPage> {
  @override
  void initState() {
    () {
      context.read<FactsProvider>().init();
    }.withPostFrameCallback();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<FactsProvider>(
      builder: (context, provider, _) {
        return PopScope(
          canPop: provider.selectedCategory == null,
          onPopInvoked: (didPop) {
            if (didPop) return;
            provider.setCategory(null);
          },
          child: Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar: AppBar(
              backgroundColor: Theme.of(context).colorScheme.primary,
              title: Text(provider.selectedCategory == null
                  ? 'About you'
                  : provider.selectedCategory == FactCategory.other
                      ? 'Other things'
                      : 'About your ${provider.selectedCategory.toString().split('.').last}'),
              leading: provider.selectedCategory != null
                  ? IconButton(
                      icon: Platform.isIOS ? const Icon(Icons.arrow_back_ios_new) : const Icon(Icons.arrow_back),
                      onPressed: () {
                        setState(() {
                          provider.setCategory(null);
                        });
                      },
                    )
                  : null,
              actions: [
                IconButton(
                  icon: const Icon(Icons.add),
                  onPressed: () {
                    _showFactDialog(context, provider);
                    MixpanelManager().factsPageCreateFactBtn();
                  },
                ),
              ],
            ),
            body: provider.loading
                ? const Center(
                    child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ))
                : provider.selectedCategory == null
                    ? _buildCategoryChips(provider)
                    : _buildFactsList(provider),
          ),
        );
      },
    );
  }

  Future<void> _showFactDialog(BuildContext context, FactsProvider provider, {Fact? fact}) async {
    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
    if (!connectivityProvider.isConnected) {
      ConnectivityProvider.showNoInternetDialog(context);
      return;
    }

    final contentController = TextEditingController(text: fact?.content.decodeString ?? '');
    final formKey = GlobalKey<FormState>();

    await showDialog(
      context: context,
      builder: (BuildContext context) {
        FactCategory selectedCategory = fact?.category ?? provider.selectedCategory ?? FactCategory.values.first;
        return StatefulBuilder(
          builder: (BuildContext context, StateSetter setModalState) {
            setCategory(FactCategory category) {
              setModalState(() {
                selectedCategory = category;
              });
            }

            return Platform.isIOS
                ? CupertinoAlertDialog(
                    content: _showFactDialogForm(formKey, contentController, selectedCategory, provider, setCategory),
                    actions: _showFactDialogActions(
                      context,
                      formKey,
                      contentController,
                      selectedCategory,
                      provider,
                      isEditing: fact != null,
                      fact: fact,
                    ),
                  )
                : AlertDialog(
                    content: _showFactDialogForm(formKey, contentController, selectedCategory, provider, setCategory),
                    actions: _showFactDialogActions(
                      context,
                      formKey,
                      contentController,
                      selectedCategory,
                      provider,
                      isEditing: fact != null,
                      fact: fact,
                    ),
                  );
          },
        );
      },
    );
  }

  Widget _showFactDialogForm(
    GlobalKey<FormState> formKey,
    TextEditingController contentController,
    FactCategory selectedCategory,
    FactsProvider provider,
    Function(FactCategory) setCategory,
  ) {
    return Form(
      key: formKey,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Platform.isIOS
              ? CupertinoTextFormFieldRow(
                  controller: contentController,
                  placeholder: 'I love Omi ...',
                  keyboardType: TextInputType.text,
                  textCapitalization: TextCapitalization.sentences,
                  textAlign: TextAlign.start,
                  placeholderStyle: const TextStyle(color: Colors.white54),
                  style: const TextStyle(color: Colors.white),
                  validator: (value) => value!.isEmpty ? 'Can\'t be empty' : null,
                  maxLines: 1,
                )
              : TextFormField(
                  controller: contentController,
                  decoration: const InputDecoration(
                    labelText: 'Fact Content',
                    hintText: 'I love Omi ...',
                    border: InputBorder.none,
                  ),
                  keyboardType: TextInputType.text,
                  textCapitalization: TextCapitalization.sentences,
                  validator: (value) => value!.isEmpty ? 'Can\'t be empty' : null,
                  maxLines: 1,
                  style: const TextStyle(color: Colors.white),
                ),
          const SizedBox(height: 16),
          Platform.isIOS
              ? CupertinoButton(
                  child: Text(
                    selectedCategory.toString().split('.').last,
                    style: const TextStyle(color: Colors.white),
                  ),
                  onPressed: () {
                    showCupertinoModalPopup(
                      context: context,
                      builder: (BuildContext context) => CupertinoActionSheet(
                        title: const Text('Select Category'),
                        actions: FactCategory.values.map((category) {
                          return CupertinoActionSheetAction(
                            child: Text(
                              category.toString().split('.').last,
                              style: const TextStyle(color: Colors.white),
                            ),
                            onPressed: () {
                              setCategory(category);
                              Navigator.pop(context);
                            },
                          );
                        }).toList(),
                        cancelButton: CupertinoActionSheetAction(
                          child: const Text(
                            'Cancel',
                            style: TextStyle(color: Colors.white),
                          ),
                          onPressed: () {
                            Navigator.pop(context);
                          },
                        ),
                      ),
                    );
                  },
                )
              : DropdownButtonFormField<FactCategory>(
                  value: selectedCategory,
                  decoration: const InputDecoration(
                    labelText: 'Category',
                  ),
                  dropdownColor: Colors.grey.shade800,
                  style: const TextStyle(color: Colors.white),
                  items: FactCategory.values.map((category) {
                    return DropdownMenuItem(
                      value: category,
                      child: Text(
                        category.toString().split('.').last,
                        style: const TextStyle(color: Colors.white),
                      ),
                    );
                  }).toList(),
                  onChanged: (value) {
                    setCategory(value!);
                  },
                ),
        ],
      ),
    );
  }

  List<Widget> _showFactDialogActions(
    BuildContext context,
    GlobalKey<FormState> formKey,
    TextEditingController contentController,
    FactCategory selectedCategory,
    FactsProvider provider, {
    bool isEditing = false,
    Fact? fact,
  }) {
    onPressed() async {
      if (formKey.currentState!.validate()) {
        if (isEditing && fact != null) {
          provider.editFactProvider(fact, contentController.text, selectedCategory);
          MixpanelManager().factsPageEditedFact();
        } else {
          provider.createFactProvider(contentController.text, selectedCategory);
          MixpanelManager().factsPageCreatedFact(selectedCategory);
        }
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
              child: Text(isEditing ? 'Update' : 'Add', style: const TextStyle(color: Colors.white)),
            ),
          ]
        : [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            TextButton(
              onPressed: onPressed,
              child: Text(isEditing ? 'Update' : 'Add', style: const TextStyle(color: Colors.white)),
            ),
          ];
  }

  Widget _buildCategoryChips(FactsProvider provider) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(32, 0, 32, 80),
      child: Align(
        alignment: Alignment.center,
        child: Wrap(
          alignment: WrapAlignment.center,
          spacing: 32,
          runSpacing: 16,
          children: provider.categories.map((item) {
            final category = item.item1;
            final count = item.item2;
            return GestureDetector(
              onTap: () {
                MixpanelManager().factsPageCategoryOpened(category);
                setState(() {
                  provider.setCategory(category);
                });
              },
              child: Container(
                decoration: BoxDecoration(
                  color: Colors.grey.shade200,
                  borderRadius: BorderRadius.circular(24),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.grey.withOpacity(0.3),
                      spreadRadius: 1,
                      blurRadius: 3,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        category.toString().split('.').last[0].toUpperCase() +
                            category.toString().split('.').last.substring(1),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.onPrimary,
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(width: 8),
                      CircleAvatar(
                        backgroundColor: Colors.black54,
                        radius: 14,
                        child: Text(
                          count.toString(),
                          style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                            fontSize: 12,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _buildFactsList(FactsProvider provider) {
    final filteredFacts = provider.filteredFacts;
    return filteredFacts.isEmpty
        ? const Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Icon(Icons.notes, size: 40),
                SizedBox(height: 24),
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: 32),
                  child: Text(
                      'Omi doesn\'t know anything about you in this realm yet. Tell it a few things to get started.',
                      style: TextStyle(color: Colors.white, fontSize: 24),
                      textAlign: TextAlign.center),
                ),
                SizedBox(height: 64),
              ],
            ),
          )
        : ListView.builder(
            itemCount: filteredFacts.length,
            itemBuilder: (context, index) {
              Fact fact = filteredFacts[index];
              return Dismissible(
                key: Key(fact.id),
                direction: DismissDirection.endToStart,
                onDismissed: (direction) {
                  provider.deleteFactProvider(fact);
                  MixpanelManager().factsPageDeletedFact(fact);
                },
                background: Container(
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.only(right: 20.0),
                  color: Colors.red,
                  child: const Icon(Icons.delete, color: Colors.white),
                ),
                child: Card(
                  color: Colors.black12,
                  elevation: 0,
                  child: Padding(
                    padding: const EdgeInsets.only(top: 16.0),
                    child: ListTile(
                      title: Text(fact.content.decodeString),
                      onTap: () => _showFactDialog(context, provider, fact: fact),
                    ),
                  ),
                ),
              );
            },
          );
  }
}
