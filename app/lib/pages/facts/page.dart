import 'dart:io';

import 'package:collection/collection.dart';
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
  static List<String> values = ["_all", ...FactCategory.values.map((c) => c.toString().split(".").last)];
  String? value = values.first;

  @override
  void initState() {
    () {
      context.read<FactsProvider>().init();
    }.withPostFrameCallback();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    List<DropdownMenuItem<String>> buildDropdownItems(FactsProvider provider) {
      String title(String val, int count) {
        if (provider.loading) {
          return val.capitalize();
        }
        return "${val.capitalize()} ($count)";
      }

      return values.map((val) {
        var count = (provider.facts.where((f) => f.category.toString().split(".").last == val)).length;
        return DropdownMenuItem<String>(
            value: val,
            child: Text(val == "_all"
                ? title("About you", provider.facts.length)
                : val == "other"
                    ? title('Other things', count)
                    : title(val, count)));
      }).toList();
    }

    return Consumer<FactsProvider>(
      builder: (context, provider, _) {
        return PopScope(
          canPop: true,
          child: Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar: AppBar(
              backgroundColor: Theme.of(context).colorScheme.primary,
              title: const Text('About you'),
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
                : RefreshIndicator(
                    color: Colors.white,
                    onRefresh: () async {
                      return await provider.loadFacts();
                    },
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      mainAxisSize: MainAxisSize.max,
                      children: [
                        _buildCategoryChips(provider),
                        provider.selectedCategory != null
                            ? Expanded(
                                child: _buildFactsList(provider),
                              )
                            : const SizedBox.shrink(),
                      ],
                    ),
                  ),
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

            return AlertDialog(
              backgroundColor: Colors.grey.shade900,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
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
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextFormField(
            controller: contentController,
            autofocus: true,
            decoration: InputDecoration(
              hintText: 'I love Omi ...',
              border: InputBorder.none,
              labelStyle: TextStyle(color: Colors.grey),
            ),
            maxLines: 5,
            minLines: 1,
            keyboardType: TextInputType.text,
            textCapitalization: TextCapitalization.sentences,
            validator: (value) => value!.isEmpty ? 'Can\'t be empty' : null,
            style: const TextStyle(color: Colors.white, fontSize: 24),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 0.0,
            runSpacing: 0.0,
            children: FactCategory.values.map((category) {
              return TextButton(
                onPressed: () {
                  setCategory(category);
                },
                child: Container(
                  decoration: BoxDecoration(
                    color: category == selectedCategory ? Colors.grey.shade800 : Colors.grey.shade900,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      category == selectedCategory
                          ? const Row(
                              children: [
                                Icon(
                                  size: 14,
                                  Icons.check,
                                  color: Colors.white,
                                ),
                                SizedBox(
                                  width: 4,
                                ),
                              ],
                            )
                          : SizedBox.shrink(),
                      Text(
                        category.toString().split('.').last,
                        style: const TextStyle(color: Colors.white),
                      ),
                    ],
                  ),
                ),
              );
            }).toList(),
          ),
          //DropdownButtonFormField<FactCategory>(
          //  value: selectedCategory,
          //  decoration: const InputDecoration(
          //    labelText: 'Category',
          //  ),
          //  dropdownColor: Colors.grey.shade800,
          //  style: const TextStyle(color: Colors.white),
          //  items: FactCategory.values.map((category) {
          //    return DropdownMenuItem(
          //      value: category,
          //      child: Text(
          //        category.toString().split('.').last,
          //        style: const TextStyle(color: Colors.white),
          //      ),
          //    );
          //  }).toList(),
          //  onChanged: (value) {
          //    setCategory(value!);
          //  },
          //),
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

    return [
      isEditing
          ? TextButton(
              onPressed: () {
                if (fact != null) {
                  provider.deleteFactProvider(fact);
                }
                Navigator.pop(context);
              },
              child: const Opacity(
                opacity: .6,
                child: Text('Delete', style: TextStyle(color: Colors.redAccent)),
              ),
            )
          : const SizedBox.shrink(),
      TextButton(
        onPressed: onPressed,
        child: Text(isEditing ? 'Update' : 'Add', style: const TextStyle(color: Colors.white)),
      ),
    ];
  }

  Widget _buildCategoryChips(FactsProvider provider) {
    Widget buildChip(item) {
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
                provider.selectedCategory == category
                    ? Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: Icon(
                          size: 16,
                          Icons.check,
                          color: Theme.of(context).colorScheme.onPrimary,
                        ))
                    : const SizedBox.shrink(),
                Text(
                  category.toString().split('.').last[0].toUpperCase() +
                      category.toString().split('.').last.substring(1),
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.onPrimary,
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: const BoxDecoration(
                    color: Colors.black54,
                    borderRadius: BorderRadius.all(Radius.circular(24)),
                  ),
                  child: Text(
                    count.toString(),
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w500,
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Padding(
      padding: provider.selectedCategory == null
          ? const EdgeInsets.fromLTRB(32, 0, 32, 80)
          : const EdgeInsets.fromLTRB(16, 32, 16, 32),
      child: Align(
        alignment: Alignment.center,
        child: Wrap(
          direction: Axis.horizontal,
          alignment: WrapAlignment.center,
          spacing: provider.selectedCategory == null ? 32 : 16,
          runSpacing: provider.selectedCategory == null ? 16 : 16,
          children: provider.categories.map((item) {
            return buildChip(item);
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
        : ListView.separated(
            separatorBuilder: (context, index) {
              return Padding(
                padding: const EdgeInsets.only(
                  left: 20,
                  right: 20,
                ),
                child: Divider(
                  color: Colors.white60,
                  height: 1,
                ),
              );
            },
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
                    padding: const EdgeInsets.only(top: 8.0, bottom: 8.0),
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
