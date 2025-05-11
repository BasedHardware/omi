import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/app_section_card.dart';
import 'package:omi/pages/apps/widgets/filter_sheet.dart';
import 'package:omi/pages/apps/list_item.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:provider/provider.dart';

import 'widgets/create_options_sheet.dart';

String filterValueToString(dynamic value) {
  if (value.runtimeType == String) {
    return value;
  } else if (value.runtimeType == Category) {
    return (value as Category).title;
  } else if (value.runtimeType == AppCapability) {
    return (value as AppCapability).title;
  }
  return '';
}

class ExploreInstallPage extends StatefulWidget {
  const ExploreInstallPage({super.key});

  @override
  State<ExploreInstallPage> createState() => _ExploreInstallPageState();
}

class _ExploreInstallPageState extends State<ExploreInstallPage> with AutomaticKeepAliveClientMixin {
  late TextEditingController searchController;
  Debouncer debouncer = Debouncer(delay: const Duration(milliseconds: 500));

  @override
  void initState() {
    searchController = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AddAppProvider>().init();
      final appProvider = context.read<AppProvider>();
      appProvider.getPopularApps().then((_) {
        print("DEBUG: Popular apps count: ${appProvider.popularApps.length}");
        if (appProvider.popularApps.isNotEmpty) {
          print("DEBUG: First popular app: ${appProvider.popularApps.first.name}");
        }
      });
    });
    super.initState();
  }

  @override
  void dispose() {
    searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Consumer<AppProvider>(builder: (context, provider, child) {
      return CustomScrollView(
        slivers: [
          const SliverToBoxAdapter(child: SizedBox(height: 18)),
          SliverToBoxAdapter(
            child: SizedBox(
              height: 50,
              child: Row(
                children: [
                  Padding(
                    padding: const EdgeInsets.only(left: 12.0),
                    child: Container(
                      decoration: BoxDecoration(
                        color: Colors.grey[800],
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: IconButton(
                        icon: const Icon(
                          Icons.filter_list_alt,
                          size: 20,
                          color: Colors.white,
                        ),
                        onPressed: () {
                          showModalBottomSheet(
                            context: context,
                            isScrollControlled: true,
                            shape: const RoundedRectangleBorder(
                              borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                            ),
                            builder: (context) => const FilterBottomSheet(),
                          ).whenComplete(() {
                            context.read<AppProvider>().filterApps();
                          });
                        },
                        tooltip: 'Filter',
                        visualDensity: VisualDensity.compact,
                        constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  provider.isFilterActive()
                      ? Expanded(
                          child: ListView.separated(
                          scrollDirection: Axis.horizontal,
                          itemBuilder: (ctx, idx) {
                            return Chip(
                              labelPadding: const EdgeInsets.symmetric(horizontal: 4),
                              label: Text(
                                filterValueToString(provider.filters.values.elementAt(idx)),
                                style: const TextStyle(fontSize: 14),
                              ),
                              deleteIcon: const Icon(Icons.close, size: 14),
                              onDeleted: () {
                                provider.removeFilter(provider.filters.keys.elementAt(idx));
                              },
                              backgroundColor: Theme.of(context).colorScheme.primaryContainer,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(8),
                              ),
                              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              visualDensity: VisualDensity.compact,
                            );
                          },
                          separatorBuilder: (ctx, idx) {
                            return const SizedBox(width: 8);
                          },
                          itemCount: provider.filters.length,
                        ))
                      : Expanded(
                          child: SizedBox(
                            height: 40,
                            child: TextFormField(
                              controller: searchController,
                              focusNode: context.read<HomeProvider>().appsSearchFieldFocusNode,
                              onChanged: (value) {
                                debouncer.run(() {
                                  provider.searchApps(value);
                                });
                              },
                              decoration: InputDecoration(
                                hintText: 'Search Apps',
                                hintStyle: TextStyle(color: Colors.white.withOpacity(0.7), fontSize: 14),
                                filled: true,
                                fillColor: Colors.grey[800],
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                  borderSide: BorderSide.none,
                                ),
                                prefixIcon: const Icon(Icons.search, color: Colors.white, size: 20),
                                suffixIcon: provider.isSearchActive()
                                    ? GestureDetector(
                                        onTap: () {
                                          context.read<HomeProvider>().appsSearchFieldFocusNode.unfocus();
                                          provider.searchApps('');
                                          searchController.clear();
                                        },
                                        child: const Icon(
                                          Icons.close,
                                          color: Colors.white,
                                          size: 20,
                                        ),
                                      )
                                    : null,
                                contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                                isDense: true,
                              ),
                              style: const TextStyle(color: Colors.white),
                            ),
                          ),
                        ),
                  const SizedBox(width: 12),
                ],
              ),
            ),
          ),
          const SliverToBoxAdapter(child: SizedBox(height: 8)),
          !provider.isFilterActive() && !provider.isSearchActive() && provider.popularApps.isNotEmpty
              ? SliverToBoxAdapter(
                  child: Container(
                    margin: const EdgeInsets.symmetric(horizontal: 12.0),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade900.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text('Popular Apps',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.bold
                                )
                              ),
                              TextButton.icon(
                                onPressed: () {
                                  // Could add a "see all popular" action here
                                },
                                icon: const Icon(Icons.arrow_forward, size: 16),
                                label: const Text('See all'),
                                style: TextButton.styleFrom(
                                  padding: const EdgeInsets.symmetric(horizontal: 8),
                                  minimumSize: const Size(0, 36),
                                ),
                              ),
                            ],
                          ),
                        ),
                        SizedBox(
                          height: 110,
                          child: ListView.builder(
                            scrollDirection: Axis.horizontal,
                            itemCount: provider.popularApps.length,
                            padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                            itemBuilder: (context, index) {
                              final app = provider.popularApps[index];
                              return Container(
                                width: 140,
                                margin: const EdgeInsets.only(right: 12),
                                decoration: BoxDecoration(
                                  color: Colors.grey.shade800.withOpacity(0.3),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: InkWell(
                                  onTap: () {
                                    // Navigate to app details
                                    Navigator.push(
                                      context,
                                      MaterialPageRoute(
                                        builder: (context) => AppDetailPage(app: app),
                                      ),
                                    );
                                  },
                                  borderRadius: BorderRadius.circular(12),
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Container(
                                        width: 56,
                                        height: 56,
                                        decoration: BoxDecoration(
                                          borderRadius: BorderRadius.circular(8),
                                          image: DecorationImage(
                                            image: NetworkImage(app.getImageUrl()),
                                            fit: BoxFit.cover,
                                          ),
                                          color: Colors.grey.shade700,
                                        ),
                                      ),
                                      const SizedBox(height: 6),
                                      Padding(
                                        padding: const EdgeInsets.symmetric(horizontal: 8.0),
                                        child: Text(
                                          app.name,
                                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                          textAlign: TextAlign.center,
                                        ),
                                      ),
                                      Text(
                                        app.getCategoryName(),
                                        style: TextStyle(fontSize: 11, color: Colors.grey.shade400),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
                        ),
                      ],
                    ),
                  ),
                )
              : const SliverToBoxAdapter(child: SizedBox.shrink()),
          const SliverToBoxAdapter(child: SizedBox(height: 8)),
          SliverToBoxAdapter(
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 12.0),
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
              decoration: BoxDecoration(
                color: Colors.grey.shade900.withOpacity(0.2),
                borderRadius: BorderRadius.only(
                  topLeft: Radius.circular(16),
                  topRight: Radius.circular(16),
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  const Text('All Apps',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold
                    )
                  ),
                  TextButton.icon(
                    onPressed: () {
                      showModalBottomSheet(
                        context: context,
                        builder: (context) => const CreateOptionsSheet(),
                        shape: const RoundedRectangleBorder(
                          borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                        ),
                      );
                    },
                    icon: const Icon(Icons.add, size: 16, color: Colors.white),
                    label: const Text('Create your own', style: TextStyle(color: Colors.white)),
                    style: TextButton.styleFrom(
                      backgroundColor: Colors.deepPurple,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          !provider.isFilterActive() && !provider.isSearchActive()
              ? Selector<AppProvider, List<App>>(
                  selector: (context, provider) => provider.apps,
                  builder: (context, apps, child) {
                    return SliverPadding(
                      padding: const EdgeInsets.symmetric(horizontal: 12.0),
                      sliver: SliverToBoxAdapter(
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.grey.shade900.withOpacity(0.2),
                            borderRadius: const BorderRadius.only(
                              bottomLeft: Radius.circular(16),
                              bottomRight: Radius.circular(16),
                            ),
                          ),
                          child: apps.isEmpty
                              ? const Padding(
                                  padding: EdgeInsets.all(16.0),
                                  child: Center(
                                    child: Text(
                                      'No apps available',
                                      style: TextStyle(fontSize: 16),
                                    ),
                                  ),
                                )
                              : ListView.builder(
                                  shrinkWrap: true,
                                  physics: const NeverScrollableScrollPhysics(),
                                  itemCount: apps.length,
                                  padding: const EdgeInsets.all(8),
                                  itemBuilder: (context, index) {
                                    final app = apps[index];
                                    return Container(
                                      margin: EdgeInsets.only(bottom: index == apps.length - 1 ? 0 : 5),
                                      decoration: BoxDecoration(
                                        color: Colors.grey.shade800.withOpacity(0.3),
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: AppListItem(
                                        app: app,
                                        index: index,
                                      ),
                                    );
                                  },
                                ),
                        ),
                      ),
                    );
                  },
                )
              : Consumer<AppProvider>(
                  builder: (context, provider, child) {
                    if (provider.filteredApps.isEmpty) {
                      return SliverToBoxAdapter(
                        child: Padding(
                          padding: EdgeInsets.only(top: MediaQuery.sizeOf(context).height * 0.10),
                          child: const Text(
                            'No apps found',
                            style: TextStyle(fontSize: 18),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      );
                    }
                    return SliverPadding(
                      padding: const EdgeInsets.symmetric(horizontal: 12.0),
                      sliver: SliverToBoxAdapter(
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.grey.shade900.withOpacity(0.2),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: ListView.builder(
                            shrinkWrap: true,
                            physics: const NeverScrollableScrollPhysics(),
                            itemCount: provider.filteredApps.length,
                            padding: const EdgeInsets.all(8),
                            itemBuilder: (context, index) {
                              final app = provider.filteredApps[index];
                              final originalIndex = provider.apps.indexWhere((a) => a.id == app.id);
                              return Container(
                                margin: EdgeInsets.only(bottom: index == provider.filteredApps.length - 1 ? 0 : 5),
                                decoration: BoxDecoration(
                                  color: Colors.grey.shade800.withOpacity(0.3),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: AppListItem(
                                  app: app,
                                  index: originalIndex,
                                ),
                              );
                            },
                          ),
                        ),
                      ),
                    );
                  },
                ),
          const SliverToBoxAdapter(child: SizedBox(height: 12)),
          SliverToBoxAdapter(
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
              decoration: BoxDecoration(
                color: Colors.red,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 16.0),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Container(
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.2),
                        shape: BoxShape.circle,
                      ),
                      padding: const EdgeInsets.all(8),
                      child: const Icon(Icons.error_outline, color: Colors.white, size: 24),
                    ),
                    const SizedBox(width: 16),
                    const Expanded(
                      child: Text(
                        'Something went wrong!\nPlease try again later.',
                        style: TextStyle(color: Colors.white, fontSize: 16, height: 1.4),
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.share, color: Colors.white),
                      onPressed: () {
                        // Share error or report issue
                      },
                      padding: EdgeInsets.zero,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      );
    });
  }

  @override
  bool get wantKeepAlive => true;
}
