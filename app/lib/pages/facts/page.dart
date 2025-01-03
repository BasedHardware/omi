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
  final Map<FactCategory, IconData> categoryIcons = {
    FactCategory.core: Icons.stars,
    FactCategory.lifestyle: Icons.local_activity,
    FactCategory.hobbies: Icons.sports_esports,
    FactCategory.interests: Icons.favorite,
    FactCategory.habits: Icons.repeat,
    FactCategory.work: Icons.work,
    FactCategory.skills: Icons.psychology,
    FactCategory.learnings: Icons.school,
    FactCategory.other: Icons.more_horiz,
  };
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
    FactCategory selectedCategory = fact?.category ?? provider.selectedCategory ?? FactCategory.values.first;

    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (BuildContext context) {
        return StatefulBuilder(
          builder: (BuildContext context, StateSetter setModalState) {
            return Container(
              height: MediaQuery.of(context).size.height * 0.8,
              decoration: const BoxDecoration(
                color: Colors.black,
                borderRadius: BorderRadius.only(
                  topLeft: Radius.circular(20),
                  topRight: Radius.circular(20),
                ),
              ),
              child: Column(
                children: [
                  // Handle bar
                  Container(
                    margin: const EdgeInsets.only(top: 8),
                    height: 4,
                    width: 40,
                    decoration: BoxDecoration(
                      color: Colors.grey.shade600,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  // Header
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        CupertinoButton(
                          padding: EdgeInsets.zero,
                          onPressed: () => Navigator.pop(context),
                          child: const Text('Cancel', style: TextStyle(color: Colors.white)),
                        ),
                        Text(
                          fact == null ? 'Add Fact' : 'Edit Fact',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 17,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        CupertinoButton(
                          padding: EdgeInsets.zero,
                          onPressed: () {
                            if (formKey.currentState!.validate()) {
                              if (fact != null) {
                                provider.editFactProvider(fact, contentController.text, selectedCategory);
                                MixpanelManager().factsPageEditedFact();
                              } else {
                                provider.createFactProvider(contentController.text, selectedCategory);
                                MixpanelManager().factsPageCreatedFact(selectedCategory);
                              }
                              Navigator.pop(context);
                            }
                          },
                          child: Text(
                            fact == null ? 'Add' : 'Save',
                            style: const TextStyle(color: Colors.white),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Divider(height: 1, color: Colors.white12),
                  Expanded(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.all(16),
                      child: Form(
                        key: formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Label for category
                            const Padding(
                              padding: EdgeInsets.only(left: 4, bottom: 8),
                              child: Text(
                                'Category',
                                style: TextStyle(
                                  color: Colors.white70,
                                  fontSize: 15,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                            // Category Selector
                            CupertinoButton(
                              padding: EdgeInsets.zero,
                              onPressed: () {
                                showCupertinoModalPopup(
                                  context: context,
                                  builder: (BuildContext context) => CupertinoActionSheet(
                                    title: const Text('Select Category'),
                                    actions: FactCategory.values.map((category) {
                                      return CupertinoActionSheetAction(
                                        onPressed: () {
                                          setModalState(() {
                                            selectedCategory = category;
                                          });
                                          Navigator.pop(context);
                                        },
                                        child: Row(
                                          mainAxisAlignment: MainAxisAlignment.center,
                                          children: [
                                            Icon(
                                              categoryIcons[category] ?? Icons.circle,
                                              color: Colors.white,
                                              size: 20,
                                            ),
                                            const SizedBox(width: 8),
                                            Text(
                                              category.toString().split('.').last[0].toUpperCase() +
                                                  category.toString().split('.').last.substring(1),
                                              style: const TextStyle(color: Colors.white),
                                            ),
                                          ],
                                        ),
                                      );
                                    }).toList(),
                                    cancelButton: CupertinoActionSheetAction(
                                      onPressed: () => Navigator.pop(context),
                                      child: Text('Cancel', style: TextStyle(color: Colors.red)),
                                    ),
                                  ),
                                );
                              },
                              child: Container(
                                padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                                decoration: BoxDecoration(
                                  color: Colors.white.withOpacity(0.1),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Row(
                                  children: [
                                    Icon(
                                      categoryIcons[selectedCategory] ?? Icons.circle,
                                      color: Colors.white,
                                      size: 20,
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: Text(
                                        selectedCategory.toString().split('.').last[0].toUpperCase() +
                                            selectedCategory.toString().split('.').last.substring(1),
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 17,
                                        ),
                                      ),
                                    ),
                                    const Icon(
                                      Icons.keyboard_arrow_down,
                                      color: Colors.white70,
                                      size: 20,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            const SizedBox(height: 24),
                            // Label for fact content
                            const Padding(
                              padding: EdgeInsets.only(left: 4, bottom: 8),
                              child: Text(
                                'Fact',
                                style: TextStyle(
                                  color: Colors.white70,
                                  fontSize: 15,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                            // Text Field
                            CupertinoTextField(
                              controller: contentController,
                              placeholder: 'Write your fact here...',
                              placeholderStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
                              style: const TextStyle(color: Colors.white),
                              maxLines: 7,
                              minLines: 3,
                              decoration: BoxDecoration(
                                color: Colors.white.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              padding: const EdgeInsets.all(12),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildCategoryChips(FactsProvider provider) {
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: provider.categories.length,
      separatorBuilder: (context, index) => const Divider(
        color: Colors.white12,
        height: 1,
      ),
      itemBuilder: (context, index) {
        final category = provider.categories[index].item1;
        final count = provider.categories[index].item2;

        return InkWell(
          onTap: () {
            MixpanelManager().factsPageCategoryOpened(category);
            setState(() {
              provider.setCategory(category);
            });
          },
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
            child: Row(
              children: [
                Icon(
                  categoryIcons[category] ?? Icons.circle,
                  color: Colors.white,
                  size: 24,
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Text(
                    category.toString().split('.').last[0].toUpperCase() +
                        category.toString().split('.').last.substring(1),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 17,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  count.toString(),
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 17,
                    fontWeight: FontWeight.w400,
                  ),
                ),
                const SizedBox(width: 8),
                const Icon(
                  Icons.chevron_right,
                  color: Colors.white30,
                  size: 24,
                ),
              ],
            ),
          ),
        );
      },
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
