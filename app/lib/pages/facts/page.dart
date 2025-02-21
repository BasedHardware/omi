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

import 'category_facts_page.dart';
import 'facts_review_page.dart';

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
    () async {
      await context.read<FactsProvider>().init();

      // Show review sheet if there are unreviewed facts
      final unreviewedFacts = context.read<FactsProvider>().unreviewed;
      print('No unreviewed facts');
      if (unreviewedFacts.isNotEmpty) {
        _showReviewSheet(unreviewedFacts);
      }
    }.withPostFrameCallback();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<FactsProvider>(
      builder: (context, provider, _) {
        return PopScope(
          canPop: true,
          child: Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar: AppBar(
              backgroundColor: Theme.of(context).colorScheme.primary,
              title: Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  const Text('My Facts'),
                  const SizedBox(height: 2),
                  Text(
                    '${provider.facts.length} total facts',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey.shade400,
                      fontWeight: FontWeight.normal,
                    ),
                  ),
                ],
              ),
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
                : CustomScrollView(
                    slivers: [
                      SliverToBoxAdapter(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                          child: SearchBar(
                            hintText: 'Search your facts',
                            leading: const Icon(Icons.search, color: Colors.white70),
                            backgroundColor: MaterialStateProperty.all(Colors.grey.shade900),
                            elevation: MaterialStateProperty.all(0),
                            padding: MaterialStateProperty.all(
                              const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                            ),
                            hintStyle: MaterialStateProperty.all(
                              TextStyle(color: Colors.grey.shade400, fontSize: 16),
                            ),
                            onChanged: (value) => provider.setSearchQuery(value),
                          ),
                        ),
                      ),
                      if (provider.searchQuery.isEmpty) ...[
                        SliverPadding(
                          padding: const EdgeInsets.fromLTRB(16, 24, 16, 16),
                          sliver: SliverGrid(
                            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: 2,
                              mainAxisSpacing: 12,
                              crossAxisSpacing: 12,
                              childAspectRatio: 2,
                            ),
                            delegate: SliverChildBuilderDelegate(
                              (context, index) {
                                final item = provider.categories[index];
                                final category = item.item1;
                                final count = item.item2;

                                return GestureDetector(
                                  onTap: () {
                                    MixpanelManager().factsPageCategoryOpened(category);
                                    provider.setCategory(category);
                                    Navigator.push(
                                      context,
                                      MaterialPageRoute(
                                        builder: (context) => CategoryFactsPage(
                                          category: category,
                                          provider: provider,
                                          showFactDialog: _showFactDialog,
                                        ),
                                      ),
                                    );
                                  },
                                  child: Container(
                                    decoration: BoxDecoration(
                                      color: Colors.grey.shade900,
                                      borderRadius: BorderRadius.circular(16),
                                    ),
                                    padding: const EdgeInsets.all(16),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          category.toString().split('.').last[0].toUpperCase() +
                                              category.toString().split('.').last.substring(1),
                                          style: const TextStyle(
                                            color: Colors.white,
                                            fontSize: 18,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                        const SizedBox(height: 8),
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                          decoration: BoxDecoration(
                                            color: Colors.black26,
                                            borderRadius: BorderRadius.circular(12),
                                          ),
                                          child: Text(
                                            count.toString(),
                                            style: const TextStyle(
                                              color: Colors.white70,
                                              fontSize: 14,
                                              fontWeight: FontWeight.w500,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                );
                              },
                              childCount: provider.categories.length,
                            ),
                          ),
                        ),
                      ] else ...[
                        SliverPadding(
                          padding: const EdgeInsets.all(16),
                          sliver: provider.filteredFacts.isEmpty
                              ? SliverFillRemaining(
                                  child: Center(
                                    child: Column(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        Icon(Icons.search_off, size: 48, color: Colors.grey.shade600),
                                        const SizedBox(height: 16),
                                        Text(
                                          'No facts found',
                                          style: TextStyle(
                                            color: Colors.grey.shade400,
                                            fontSize: 18,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                )
                              : SliverList(
                                  delegate: SliverChildBuilderDelegate(
                                    (context, index) {
                                      final fact = provider.filteredFacts[index];
                                      return Dismissible(
                                        key: Key(fact.id),
                                        direction: DismissDirection.endToStart,
                                        onDismissed: (direction) {
                                          provider.deleteFactProvider(fact);
                                          MixpanelManager().factsPageDeletedFact(fact);
                                        },
                                        background: Container(
                                          margin: const EdgeInsets.only(bottom: 8),
                                          decoration: BoxDecoration(
                                            color: Colors.red.shade900,
                                            borderRadius: BorderRadius.circular(12),
                                          ),
                                          alignment: Alignment.centerRight,
                                          padding: const EdgeInsets.only(right: 20),
                                          child: const Icon(Icons.delete_outline, color: Colors.white),
                                        ),
                                        child: GestureDetector(
                                          onTap: () => _showQuickEditSheet(context, fact, provider),
                                          child: Container(
                                            margin: const EdgeInsets.only(bottom: 8),
                                            decoration: BoxDecoration(
                                              color: Colors.grey.shade900,
                                              borderRadius: BorderRadius.circular(12),
                                            ),
                                            child: ListTile(
                                              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                                              title: Text(
                                                fact.content.decodeString,
                                                style: const TextStyle(
                                                  color: Colors.white,
                                                  fontSize: 16,
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                      );
                                    },
                                    childCount: provider.filteredFacts.length,
                                  ),
                                ),
                        ),
                      ],
                    ],
                  ),
          ),
        );
      },
    );
  }

  void _showQuickEditSheet(BuildContext context, Fact fact, FactsProvider provider) {
    final contentController = TextEditingController(text: fact.content.decodeString);
    contentController.selection = TextSelection.fromPosition(
      TextPosition(offset: contentController.text.length),
    );

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
        child: Container(
          decoration: BoxDecoration(
            color: Colors.grey.shade900,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.label_outline, size: 14, color: Colors.white),
                        const SizedBox(width: 4),
                        Text(
                          fact.category.toString().split('.').last,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 14,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.delete_outline, color: Colors.red),
                    onPressed: () => _showDeleteConfirmation(context, fact, provider),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                controller: contentController,
                autofocus: true,
                maxLines: null,
                textInputAction: TextInputAction.done,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  height: 1.4,
                ),
                decoration: const InputDecoration(
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.zero,
                  isDense: true,
                ),
                onSubmitted: (value) {
                  if (value.trim().isNotEmpty) {
                    provider.editFactProvider(fact, value, fact.category);
                  }
                  Navigator.pop(context);
                },
                onChanged: (value) {
                  if (value.trim().isNotEmpty) {
                    provider.editFactProvider(fact, value, fact.category);
                  }
                },
              ),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.05),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.keyboard_return,
                          size: 13,
                          color: Colors.grey.shade400,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          'Press done to save',
                          style: TextStyle(
                            color: Colors.grey.shade400,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    '${contentController.text.length}/200',
                    style: TextStyle(
                      color: Colors.grey.shade500,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showFactDialog(BuildContext context, FactsProvider provider, {Fact? fact}) async {
    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
    if (!connectivityProvider.isConnected) {
      ConnectivityProvider.showNoInternetDialog(context);
      return;
    }

    final contentController = TextEditingController(text: fact?.content.decodeString ?? '');
    contentController.selection = TextSelection.fromPosition(
      TextPosition(offset: contentController.text.length),
    );

    FactCategory selectedCategory = fact?.category ?? provider.selectedCategory ?? FactCategory.values.first;

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => Padding(
          padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
          child: Container(
            decoration: BoxDecoration(
              color: Colors.grey.shade900,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
            ),
            padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      fact != null ? 'Edit Fact' : 'New Fact',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (fact != null)
                      IconButton(
                        icon: const Icon(Icons.delete_outline, color: Colors.red, size: 22),
                        onPressed: () => _showDeleteConfirmation(context, fact, provider),
                      ),
                  ],
                ),
                if (fact == null || !fact.manuallyAdded) ...[
                  const SizedBox(height: 16),
                  SizedBox(
                    height: 34,
                    child: ListView.separated(
                      scrollDirection: Axis.horizontal,
                      itemCount: FactCategory.values.length,
                      separatorBuilder: (context, _) => const SizedBox(width: 8),
                      itemBuilder: (context, index) {
                        final category = FactCategory.values[index];
                        final isSelected = category == selectedCategory;
                        return GestureDetector(
                          onTap: () => setState(() => selectedCategory = category),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                            decoration: BoxDecoration(
                              color: isSelected ? Colors.white.withOpacity(0.1) : Colors.grey.shade800,
                              borderRadius: BorderRadius.circular(17),
                              border: Border.all(
                                color: isSelected ? Colors.white : Colors.transparent,
                                width: 1,
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                if (isSelected) ...[
                                  const Icon(
                                    Icons.check,
                                    size: 14,
                                    color: Colors.white,
                                  ),
                                  const SizedBox(width: 4),
                                ],
                                Text(
                                  category.toString().split('.').last,
                                  style: TextStyle(
                                    color: isSelected ? Colors.white : Colors.white70,
                                    fontSize: 13,
                                    fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                ],
                const SizedBox(height: 24),
                Container(
                  decoration: BoxDecoration(
                    color: Colors.grey.shade800,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  child: TextField(
                    controller: contentController,
                    textInputAction: TextInputAction.done,
                    autofocus: true,
                    maxLines: null,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      height: 1.4,
                    ),
                    decoration: const InputDecoration(
                      hintText: 'I like to eat ice cream...',
                      hintStyle: TextStyle(color: Colors.grey),
                      border: InputBorder.none,
                      contentPadding: EdgeInsets.zero,
                      isDense: true,
                    ),
                    onSubmitted: (value) {
                      if (value.trim().isNotEmpty) {
                        if (fact != null) {
                          provider.editFactProvider(fact, value, selectedCategory);
                          MixpanelManager().factsPageEditedFact();
                        } else {
                          provider.createFactProvider(value, selectedCategory);
                          MixpanelManager().factsPageCreatedFact(selectedCategory);
                        }
                        Navigator.pop(context);
                      }
                    },
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.05),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.keyboard_return,
                            size: 13,
                            color: Colors.grey.shade400,
                          ),
                          const SizedBox(width: 4),
                          Text(
                            'Press done to save',
                            style: TextStyle(
                              color: Colors.grey.shade400,
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Text(
                      '${contentController.text.length}/200',
                      style: TextStyle(
                        color: Colors.grey.shade500,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _showDeleteConfirmation(BuildContext context, Fact fact, FactsProvider provider) {
    if (Platform.isIOS) {
      showCupertinoDialog(
        context: context,
        builder: (context) => CupertinoAlertDialog(
          title: const Text('Delete fact?'),
          content: const Text('This action cannot be undone.'),
          actions: [
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.pop(context),
              child: Text(
                'Cancel',
                style: TextStyle(color: Colors.grey.shade400),
              ),
            ),
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () {
                provider.deleteFactProvider(fact);
                Navigator.pop(context); // Close dialog
                Navigator.pop(context); // Close edit sheet
              },
              child: const Text('Delete'),
            ),
          ],
        ),
      );
    } else {
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          backgroundColor: Colors.grey.shade900,
          surfaceTintColor: Colors.transparent,
          title: const Text(
            'Delete fact?',
            style: TextStyle(color: Colors.white, fontSize: 18),
          ),
          content: const Text(
            'This action cannot be undone.',
            style: TextStyle(color: Colors.white70, fontSize: 14),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(
                'Cancel',
                style: TextStyle(color: Colors.grey.shade400),
              ),
            ),
            TextButton(
              onPressed: () {
                provider.deleteFactProvider(fact);
                Navigator.pop(context); // Close dialog
                Navigator.pop(context); // Close edit sheet
              },
              child: const Text(
                'Delete',
                style: TextStyle(color: Colors.red),
              ),
            ),
          ],
        ),
      );
    }
  }

  void _showReviewSheet(List<Fact> facts) async {
    if (facts.isEmpty) return;
    await showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isDismissible: true,
      enableDrag: false,
      builder: (context) => ListenableProvider(
          create: (_) => FactsProvider(),
          builder: (context, _) {
            return FactReviewSheet(
              facts: facts,
              provider: context.read<FactsProvider>(),
            );
          }),
    );
  }
}

class FactReviewSheet extends StatelessWidget {
  final List<Fact> facts;
  final FactsProvider provider;

  const FactReviewSheet({
    super.key,
    required this.facts,
    required this.provider,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(24),
            margin: const EdgeInsets.only(bottom: 20),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(
                          width: MediaQuery.of(context).size.width * 0.74,
                          child: Text(
                            'Review and save ${facts.length} facts generated from today\'s conversation with Omi',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w400,
                            ),
                          ),
                        ),
                        const SizedBox(height: 4),
                        // Text(
                        //   '${facts.length} facts to review',
                        //   style: TextStyle(
                        //     color: Colors.grey.shade400,
                        //     fontSize: 14,
                        //   ),
                        // ),
                      ],
                    ),
                    IconButton(
                      icon: const Icon(Icons.close, color: Colors.white70),
                      onPressed: () => Navigator.pop(context),
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      child: TextButton(
                        style: TextButton.styleFrom(
                          backgroundColor: Colors.white.withOpacity(0.1),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        onPressed: () => Navigator.pop(context),
                        child: Text(
                          'Review later',
                          style: TextStyle(
                            color: Colors.grey.shade300,
                            fontSize: 15,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextButton(
                        style: TextButton.styleFrom(
                          backgroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        onPressed: () {
                          Navigator.pop(context);
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (context) => FactReviewPage(
                                facts: facts,
                                provider: provider,
                              ),
                            ),
                          );
                        },
                        child: const Text(
                          'Review now',
                          style: TextStyle(
                            color: Colors.black,
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
