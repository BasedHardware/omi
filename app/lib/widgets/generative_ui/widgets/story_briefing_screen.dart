import 'package:flutter/material.dart';
import '../models/story_briefing_data.dart';
import '../models/timeline_data.dart';
import '../models/quote_board_data.dart';
import '../models/followups_data.dart';

/// Full-screen story briefing with tabbed navigation
/// Follows the same visual language as other generative UI components
class StoryBriefingScreen extends StatefulWidget {
  final StoryBriefingData data;

  const StoryBriefingScreen({
    super.key,
    required this.data,
  });

  @override
  State<StoryBriefingScreen> createState() => _StoryBriefingScreenState();
}

class _StoryBriefingScreenState extends State<StoryBriefingScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  late List<_BriefingTab> _tabs;

  @override
  void initState() {
    super.initState();
    _buildTabs();
    _tabController = TabController(length: _tabs.length, vsync: this);
  }

  void _buildTabs() {
    _tabs = [];
    if (widget.data.hasTimeline) {
      _tabs.add(_BriefingTab(
        icon: Icons.timeline,
        label: 'Timeline',
        count: widget.data.timeline!.events.length,
      ));
    }
    if (widget.data.hasQuotes) {
      _tabs.add(_BriefingTab(
        icon: Icons.format_quote,
        label: 'Quotes',
        count: widget.data.quoteBoard!.quotes.length,
      ));
    }
    if (widget.data.hasFollowups) {
      _tabs.add(_BriefingTab(
        icon: Icons.checklist_rounded,
        label: 'Follow-ups',
        count: widget.data.followups!.items.length,
      ));
    }
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          children: [
            // Header
            _buildHeader(context),

            // Tab bar
            _buildTabBar(),

            // Tab content
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: _buildTabViews(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 8, 16, 16),
      child: Row(
        children: [
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.arrow_back, color: Colors.white),
          ),
          const SizedBox(width: 4),
          Icon(
            Icons.article_outlined,
            color: Colors.white.withOpacity(0.6),
            size: 20,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Story Briefing',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  widget.data.summary,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.5),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTabBar() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.05),
        borderRadius: BorderRadius.circular(12),
      ),
      child: TabBar(
        controller: _tabController,
        indicator: BoxDecoration(
          color: Colors.white.withOpacity(0.1),
          borderRadius: BorderRadius.circular(10),
        ),
        indicatorSize: TabBarIndicatorSize.tab,
        indicatorPadding: const EdgeInsets.all(4),
        labelColor: Colors.white,
        unselectedLabelColor: Colors.white.withOpacity(0.5),
        dividerColor: Colors.transparent,
        tabs: _tabs.map((tab) => _buildTab(tab)).toList(),
      ),
    );
  }

  Widget _buildTab(_BriefingTab tab) {
    return Tab(
      height: 48,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(tab.icon, size: 16),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              tab.label,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 4),
          Text(
            '${tab.count}',
            style: TextStyle(
              fontSize: 11,
              color: Colors.white.withOpacity(0.5),
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _buildTabViews() {
    final views = <Widget>[];

    if (widget.data.hasTimeline) {
      views.add(_TimelineTabView(data: widget.data.timeline!));
    }
    if (widget.data.hasQuotes) {
      views.add(_QuotesTabView(data: widget.data.quoteBoard!));
    }
    if (widget.data.hasFollowups) {
      views.add(_FollowupsTabView(data: widget.data.followups!));
    }

    return views;
  }
}

class _BriefingTab {
  final IconData icon;
  final String label;
  final int count;

  const _BriefingTab({
    required this.icon,
    required this.label,
    required this.count,
  });
}

// ============================================================================
// Timeline Tab View
// ============================================================================

class _TimelineTabView extends StatelessWidget {
  final TimelineDisplayData data;

  const _TimelineTabView({required this.data});

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: data.events.length,
      itemBuilder: (context, index) {
        final event = data.events[index];
        final isLast = index == data.events.length - 1;
        return _TimelineEventItem(event: event, isLast: isLast);
      },
    );
  }
}

class _TimelineEventItem extends StatelessWidget {
  final TimelineEventData event;
  final bool isLast;

  const _TimelineEventItem({
    required this.event,
    required this.isLast,
  });

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Timeline line and dot
          SizedBox(
            width: 24,
            child: Column(
              children: [
                const SizedBox(height: 6),
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: event.labelType.color,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: event.labelType.color.withOpacity(0.4),
                        blurRadius: 4,
                        spreadRadius: 1,
                      ),
                    ],
                  ),
                ),
                if (!isLast)
                  Expanded(
                    child: Container(
                      width: 2,
                      color: Colors.white.withOpacity(0.2),
                    ),
                  ),
              ],
            ),
          ),

          const SizedBox(width: 12),

          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Time and label row
                  Row(
                    children: [
                      if (event.time.isNotEmpty) ...[
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.white.withOpacity(0.1),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            event.time,
                            style: TextStyle(
                              color: Colors.white.withOpacity(0.7),
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              fontFeatures: const [FontFeature.tabularFigures()],
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                      ],
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 3,
                        ),
                        decoration: BoxDecoration(
                          color: event.labelType.color.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          event.label,
                          style: TextStyle(
                            color: event.labelType.color,
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 6),

                  Text(
                    event.description,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.9),
                      fontSize: 15,
                      height: 1.5,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================================
// Quotes Tab View
// ============================================================================

class _QuotesTabView extends StatelessWidget {
  final QuoteBoardDisplayData data;

  const _QuotesTabView({required this.data});

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: data.quotes.length,
      itemBuilder: (context, index) {
        final quote = data.quotes[index];
        return _QuoteBubble(quote: quote);
      },
    );
  }
}

class _QuoteBubble extends StatelessWidget {
  final QuoteData quote;

  const _QuoteBubble({required this.quote});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Speech bubble
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.08),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(4),
                topRight: Radius.circular(18),
                bottomLeft: Radius.circular(18),
                bottomRight: Radius.circular(18),
              ),
            ),
            child: Text(
              quote.quote.replaceAll(RegExp(r'^\"|\"$'), ''),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 15,
                height: 1.5,
              ),
            ),
          ),

          const SizedBox(height: 8),

          // Attribution row
          Padding(
            padding: const EdgeInsets.only(left: 4),
            child: Row(
              children: [
                Text(
                  '— ${quote.speaker}',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                if (quote.time.isNotEmpty) ...[
                  Text(
                    ' · ',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.3),
                      fontSize: 13,
                    ),
                  ),
                  Text(
                    quote.time,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.4),
                      fontSize: 12,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                ],
                if (quote.recordStatus != QuoteRecordStatus.onTheRecord) ...[
                  Text(
                    ' · ',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.3),
                      fontSize: 13,
                    ),
                  ),
                  Text(
                    quote.recordStatus.displayName,
                    style: TextStyle(
                      color: quote.recordStatus.color.withOpacity(0.7),
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================================
// Follow-ups Tab View
// ============================================================================

class _FollowupsTabView extends StatelessWidget {
  final FollowupsDisplayData data;

  const _FollowupsTabView({required this.data});

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: data.items.length,
      itemBuilder: (context, index) {
        final item = data.items[index];
        final isLast = index == data.items.length - 1;
        return _FollowupItem(item: item, isLast: isLast);
      },
    );
  }
}

class _FollowupItem extends StatelessWidget {
  final FollowupItemData item;
  final bool isLast;

  const _FollowupItem({
    required this.item,
    required this.isLast,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: isLast ? 0 : 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Colored dot indicator
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: item.type.color,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: item.type.color.withOpacity(0.4),
                    blurRadius: 4,
                    spreadRadius: 1,
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(width: 12),

          // Content
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Type badge
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 3,
                  ),
                  decoration: BoxDecoration(
                    color: item.type.backgroundColor,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    item.type.displayName,
                    style: TextStyle(
                      color: item.type.color,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),

                const SizedBox(height: 6),

                // Task text
                Text(
                  item.content,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.9),
                    fontSize: 15,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
