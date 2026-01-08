import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:latlong2/latlong.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/http/api/conversations.dart' as conversations_api;
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/maps_util.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class DailySummaryDetailPage extends StatefulWidget {
  final String summaryId;
  final DailySummary? summary; // Can pass directly if already loaded

  const DailySummaryDetailPage({
    super.key,
    required this.summaryId,
    this.summary,
  });

  @override
  State<DailySummaryDetailPage> createState() => _DailySummaryDetailPageState();
}

class _DailySummaryDetailPageState extends State<DailySummaryDetailPage> with SingleTickerProviderStateMixin {
  DailySummary? _summary;
  bool _isLoading = true;
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _fadeAnimation = CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOut,
    );
    _loadSummary();
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  Future<void> _loadSummary() async {
    if (widget.summary != null) {
      setState(() {
        _summary = widget.summary;
        _isLoading = false;
      });
      _animationController.forward();
      // Track page view
      MixpanelManager().dailySummaryDetailViewed(
        summaryId: widget.summaryId,
        date: widget.summary!.date,
        source: 'direct',
      );
      return;
    }

    final summary = await getDailySummary(widget.summaryId);
    if (mounted) {
      setState(() {
        _summary = summary;
        _isLoading = false;
      });
      _animationController.forward();
      // Track page view
      if (summary != null) {
        MixpanelManager().dailySummaryDetailViewed(
          summaryId: widget.summaryId,
          date: summary.date,
          source: 'api_fetch',
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: Colors.white))
          : _summary == null
              ? _buildNotFound()
              : _buildContent(),
    );
  }

  Future<void> _openConversation(String? conversationId) async {
    if (conversationId == null || conversationId.isEmpty) return;

    // Track conversation click
    if (_summary != null) {
      MixpanelManager().dailySummaryConversationClicked(
        summaryId: widget.summaryId,
        conversationId: conversationId,
        source: 'daily_summary_detail',
      );
    }

    // Show loading indicator
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => const Center(
        child: CircularProgressIndicator(color: Colors.white),
      ),
    );

    try {
      final conversation = await conversations_api.getConversationById(conversationId);
      if (!mounted) return;
      Navigator.pop(context); // Dismiss loading

      if (conversation != null) {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => ConversationDetailPage(conversation: conversation),
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      Navigator.pop(context); // Dismiss loading
    }
  }

  Widget _buildNotFound() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Text(
            '📭',
            style: TextStyle(fontSize: 64),
          ),
          const SizedBox(height: 16),
          Text(
            'Summary not found',
            style: TextStyle(
              color: Colors.grey.shade400,
              fontSize: 18,
            ),
          ),
          const SizedBox(height: 24),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Go Back'),
          ),
        ],
      ),
    );
  }

  Widget _buildContent() {
    final summary = _summary!;
    return FadeTransition(
      opacity: _fadeAnimation,
      child: CustomScrollView(
        slivers: [
          _buildHeader(summary),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 100),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                _buildOverviewCard(summary),
                const SizedBox(height: 24),
                _buildStatsRow(summary),
                if (summary.highlights.isNotEmpty) ...[
                  const SizedBox(height: 32),
                  _buildHighlightsSection(summary),
                ],
                if (summary.actionItems.isNotEmpty) ...[
                  const SizedBox(height: 32),
                  _buildActionItemsSection(summary),
                ],
                if (summary.unresolvedQuestions.isNotEmpty) ...[
                  const SizedBox(height: 32),
                  _buildUnresolvedQuestionsSection(summary),
                ],
                if (summary.decisionsMade.isNotEmpty) ...[
                  const SizedBox(height: 32),
                  _buildDecisionsMadeSection(summary),
                ],
                if (summary.knowledgeNuggets.isNotEmpty) ...[
                  const SizedBox(height: 32),
                  _buildKnowledgeNuggetsSection(summary),
                ],
                if (summary.locations.isNotEmpty) ...[
                  const SizedBox(height: 32),
                  _buildLocationsMap(summary),
                ],
              ]),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader(DailySummary summary) {
    return SliverAppBar(
      expandedHeight: 150,
      pinned: true,
      backgroundColor: Theme.of(context).colorScheme.primary,
      leading: IconButton(
        icon: Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: Colors.black.withOpacity(0.3),
            shape: BoxShape.circle,
          ),
          child: const Icon(Icons.arrow_back, color: Colors.white, size: 20),
        ),
        onPressed: () => Navigator.pop(context),
      ),
      flexibleSpace: FlexibleSpaceBar(
        background: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Color(0xFF2D1F5B), // Deep purple at top
                Color(0xFF000000), // Almost black at bottom
              ],
            ),
          ),
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  const Spacer(),
                  // Date above emoji and title
                  Text(
                    summary.formattedDate,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.6),
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 8),
                  // Emoji and title row
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        summary.dayEmoji,
                        style: const TextStyle(fontSize: 32),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          summary.headline,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                            height: 1.2,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildOverviewCard(DailySummary summary) {
    return Text(
      summary.overview,
      style: TextStyle(
        color: Colors.grey.shade300,
        fontSize: 15,
        height: 1.5,
      ),
    );
  }

  Widget _buildStatsRow(DailySummary summary) {
    return Row(
      children: [
        _buildStatItem(FontAwesomeIcons.message, '${summary.stats.totalConversations}'),
        const SizedBox(width: 8),
        _buildStatItem(FontAwesomeIcons.clock, summary.stats.formattedDuration),
        const SizedBox(width: 8),
        _buildStatItem(FontAwesomeIcons.circleCheck, '${summary.stats.actionItemsCount}'),
      ],
    );
  }

  Widget _buildStatItem(IconData icon, String value) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
        decoration: BoxDecoration(
          color: const Color(0xFF1A1A1F),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            FaIcon(icon, color: Colors.grey.shade400, size: 14),
            const SizedBox(width: 8),
            Text(
              value,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // Get short name from full address (first part before comma)
  String _getShortLocationName(String? address) {
    if (address == null || address.isEmpty) return 'Unknown';
    final parts = address.split(',');
    return parts.first.trim();
  }

  // Get truly unique location count (by short name)
  int _getUniqueLocationCount(List<LocationPin> locations) {
    final uniqueNames = <String>{};
    for (final loc in locations) {
      uniqueNames.add(_getShortLocationName(loc.address));
    }
    return uniqueNames.length;
  }

  // Parse time string to minutes for comparison (e.g., "14:42" -> 882)
  int _parseTimeToMinutes(String? timeStr) {
    if (timeStr == null || timeStr.isEmpty) return 0;
    final parts = timeStr.split(':');
    if (parts.length != 2) return 0;
    final hours = int.tryParse(parts[0]) ?? 0;
    final minutes = int.tryParse(parts[1]) ?? 0;
    return hours * 60 + minutes;
  }

  // Format time from "17:00" to "5PM" format
  String _formatTimeTo12Hour(String? timeStr) {
    if (timeStr == null || timeStr.isEmpty) return '';
    final parts = timeStr.split(':');
    if (parts.length != 2) return timeStr;
    final hours = int.tryParse(parts[0]) ?? 0;
    final minutes = int.tryParse(parts[1]) ?? 0;
    final period = hours >= 12 ? 'PM' : 'AM';
    final hour12 = hours == 0 ? 12 : (hours > 12 ? hours - 12 : hours);
    if (minutes == 0) {
      return '$hour12$period';
    } else {
      return '$hour12:${minutes.toString().padLeft(2, '0')}$period';
    }
  }

  // Merge adjacent same locations and return timeline data (chronologically sorted)
  List<_TimelineLocation> _buildTimelineLocations(List<LocationPin> locations) {
    if (locations.isEmpty) return [];

    // Sort locations by time chronologically (earliest first)
    final sortedLocations = List<LocationPin>.from(locations);
    sortedLocations.sort((a, b) => _parseTimeToMinutes(a.time).compareTo(_parseTimeToMinutes(b.time)));

    final timeline = <_TimelineLocation>[];
    _TimelineLocation? current;

    for (final loc in sortedLocations) {
      final shortName = _getShortLocationName(loc.address);

      if (current == null || current.shortName != shortName) {
        // New location (different from previous)
        current = _TimelineLocation(
          shortName: shortName,
          fullAddress: loc.address,
          latitude: loc.latitude,
          longitude: loc.longitude,
          startTime: loc.time,
          endTime: loc.time,
        );
        timeline.add(current);
      } else {
        // Same location as previous, extend the end time
        current.endTime = loc.time;
      }
    }

    return timeline;
  }

  Widget _buildLocationsMap(DailySummary summary) {
    // Build timeline with merged adjacent locations
    final timelineLocations = _buildTimelineLocations(summary.locations);

    // Get all coordinates as LatLng
    final points = summary.locations.map((l) => LatLng(l.latitude, l.longitude)).toList();

    // Calculate bounds to fit all markers
    final minLat = summary.locations.map((l) => l.latitude).reduce((a, b) => a < b ? a : b);
    final maxLat = summary.locations.map((l) => l.latitude).reduce((a, b) => a > b ? a : b);
    final minLng = summary.locations.map((l) => l.longitude).reduce((a, b) => a < b ? a : b);
    final maxLng = summary.locations.map((l) => l.longitude).reduce((a, b) => a > b ? a : b);

    // Add padding to bounds (in degrees) to ensure pins aren't at the edge
    const padding = 0.01; // ~1km padding
    final bounds = LatLngBounds(
      LatLng(minLat - padding, minLng - padding),
      LatLng(maxLat + padding, maxLng + padding),
    );

    // For single location, use center + zoom; for multiple, use bounds
    final bool singleLocation = summary.locations.length == 1;
    final centerLat = (minLat + maxLat) / 2;
    final centerLng = (minLng + maxLng) / 2;

    // Build markers for FlutterMap
    final markers = summary.locations.map((loc) {
      return Marker(
        point: LatLng(loc.latitude, loc.longitude),
        width: 32,
        height: 32,
        child: const FaIcon(
          FontAwesomeIcons.locationDot,
          color: Colors.deepPurple,
          size: 28,
        ),
      );
    }).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle('Your Day\'s Journey'),
        const SizedBox(height: 16),
        ClipRRect(
          borderRadius: BorderRadius.circular(24),
          child: GestureDetector(
            onTap: () {
              if (summary.locations.isNotEmpty) {
                MapsUtil.launchMap(summary.locations.first.latitude, summary.locations.first.longitude);
              }
            },
            child: SizedBox(
              width: double.infinity,
              height: 200,
              child: IgnorePointer(
                child: FlutterMap(
                  options: MapOptions(
                    initialCenter: singleLocation ? points.first : LatLng(centerLat, centerLng),
                    initialZoom: singleLocation ? 14 : 12,
                    // Use bounds fitting for multiple locations
                    initialCameraFit: singleLocation
                        ? null
                        : CameraFit.bounds(
                            bounds: bounds,
                            padding: const EdgeInsets.all(50),
                          ),
                    interactionOptions: const InteractionOptions(
                      flags: InteractiveFlag.none,
                    ),
                  ),
                  children: [
                    TileLayer(
                      urlTemplate: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
                      subdomains: const ['a', 'b', 'c', 'd'],
                      userAgentPackageName: 'me.omi.app',
                      retinaMode: true,
                    ),
                    MarkerLayer(markers: markers),
                  ],
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        // Timeline list
        ...timelineLocations.asMap().entries.map((entry) {
          final index = entry.key;
          final location = entry.value;
          final isFirst = index == 0;
          final isLast = index == timelineLocations.length - 1;

          return _buildTimelineItem(location, isFirst, isLast);
        }),
      ],
    );
  }

  Widget _buildHighlightsSection(DailySummary summary) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle('Highlights'),
        const SizedBox(height: 12),
        ...summary.highlights.map((highlight) {
          return GestureDetector(
            onTap: () {
              if (highlight.conversationIds.isNotEmpty) {
                _openConversation(highlight.conversationIds.first);
              }
            },
            child: Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A1F),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(highlight.emoji, style: const TextStyle(fontSize: 20)),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          highlight.topic,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          highlight.summary,
                          style: TextStyle(
                            color: Colors.grey.shade400,
                            fontSize: 13,
                            height: 1.3,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (highlight.conversationIds.isNotEmpty)
                    Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 18),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildActionItemsSection(DailySummary summary) {
    // Separate completed and incomplete items
    final incompleteItems = summary.actionItems.where((i) => !i.completed).toList();
    final completedItems = summary.actionItems.where((i) => i.completed).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            _buildSectionTitle('Tasks'),
            const Spacer(),
            if (completedItems.isNotEmpty)
              Text(
                '${completedItems.length}/${summary.actionItems.length}',
                style: TextStyle(
                  color: Colors.grey.shade500,
                  fontSize: 13,
                ),
              ),
          ],
        ),
        const SizedBox(height: 12),
        // Show incomplete items first, then completed
        ...[...incompleteItems, ...completedItems].map((item) {
          return _buildActionItemRow(item);
        }),
      ],
    );
  }

  Widget _buildActionItemRow(ActionItemSummary item) {
    return GestureDetector(
      onTap: () => _openConversation(item.sourceConversationId),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: const Color(0xFF1A1A1F),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            // Checkbox indicator
            Container(
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: item.completed ? Colors.green.withOpacity(0.2) : Colors.transparent,
                border: Border.all(
                  color: item.completed ? Colors.green : Colors.grey.shade600,
                  width: 1.5,
                ),
              ),
              child: item.completed ? const Icon(Icons.check, color: Colors.green, size: 14) : null,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                item.description,
                style: TextStyle(
                  color: item.completed ? Colors.grey.shade500 : Colors.white,
                  fontSize: 15,
                  height: 1.4,
                  decoration: item.completed ? TextDecoration.lineThrough : null,
                ),
              ),
            ),
            if (item.sourceConversationId != null) Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 20),
          ],
        ),
      ),
    );
  }

  Color _getPriorityColor(String priority) {
    switch (priority.toLowerCase()) {
      case 'high':
        return const Color(0xFFFF6B6B);
      case 'medium':
        return const Color(0xFFFFB347);
      default:
        return const Color(0xFF6BCB77);
    }
  }

  Widget _buildUnresolvedQuestionsSection(DailySummary summary) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle('Unresolved Questions'),
        const SizedBox(height: 12),
        ...summary.unresolvedQuestions.map((q) {
          return GestureDetector(
            onTap: () => _openConversation(q.conversationId),
            child: Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A1F),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      q.question,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        height: 1.4,
                      ),
                    ),
                  ),
                  if (q.conversationId != null) Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 20),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildDecisionsMadeSection(DailySummary summary) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle('Decisions'),
        const SizedBox(height: 12),
        ...summary.decisionsMade.map((d) {
          return GestureDetector(
            onTap: () => _openConversation(d.conversationId),
            child: Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A1F),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      d.decision,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        height: 1.4,
                      ),
                    ),
                  ),
                  if (d.conversationId != null) Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 20),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildKnowledgeNuggetsSection(DailySummary summary) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionTitle('Learnings'),
        const SizedBox(height: 12),
        ...summary.knowledgeNuggets.map((k) {
          return GestureDetector(
            onTap: () => _openConversation(k.conversationId),
            child: Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A1F),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      k.insight,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        height: 1.4,
                      ),
                    ),
                  ),
                  if (k.conversationId != null) Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 20),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildSectionTitle(String title) {
    return Text(
      title,
      style: const TextStyle(
        color: Colors.white,
        fontSize: 18,
        fontWeight: FontWeight.w600,
      ),
    );
  }

  Widget _buildTimelineItem(_TimelineLocation location, bool isFirst, bool isLast) {
    final startFormatted = _formatTimeTo12Hour(location.startTime);
    final endFormatted = _formatTimeTo12Hour(location.endTime);
    final timeText = startFormatted.isNotEmpty
        ? (endFormatted.isNotEmpty && startFormatted != endFormatted
            ? '$startFormatted - $endFormatted'
            : startFormatted)
        : '';

    return GestureDetector(
      onTap: () => MapsUtil.launchMap(location.latitude, location.longitude),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Timeline line and dot
            SizedBox(
              width: 40,
              child: Column(
                children: [
                  // Top line (hidden for first item)
                  Container(
                    width: 2,
                    height: 12,
                    color: isFirst ? Colors.transparent : Colors.deepPurple.withOpacity(0.4),
                  ),
                  // Dot
                  Container(
                    width: 14,
                    height: 14,
                    decoration: BoxDecoration(
                      color: Colors.deepPurple,
                      shape: BoxShape.circle,
                      border: Border.all(color: const Color(0xFF0A0A0A), width: 2),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.deepPurple.withOpacity(0.4),
                          blurRadius: 6,
                          spreadRadius: 1,
                        ),
                      ],
                    ),
                  ),
                  // Bottom line (hidden for last item)
                  Expanded(
                    child: Container(
                      width: 2,
                      color: isLast ? Colors.transparent : Colors.deepPurple.withOpacity(0.4),
                    ),
                  ),
                ],
              ),
            ),
            // Content
            Expanded(
              child: Container(
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.fromLTRB(18, 14, 18, 14),
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A1F),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            location.shortName,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                              height: 1.4,
                            ),
                          ),
                          if (timeText.isNotEmpty) ...[
                            const SizedBox(height: 4),
                            Row(
                              children: [
                                FaIcon(
                                  FontAwesomeIcons.clock,
                                  color: Colors.grey.shade500,
                                  size: 12,
                                ),
                                const SizedBox(width: 4),
                                Padding(
                                  padding: const EdgeInsets.only(top: 2),
                                  child: Text(
                                    timeText,
                                    style: TextStyle(
                                      color: Colors.grey.shade500,
                                      fontSize: 13,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                    ),
                    Icon(Icons.chevron_right, color: Colors.grey.shade600, size: 20),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// Helper class for timeline locations
class _TimelineLocation {
  final String shortName;
  final String? fullAddress;
  final double latitude;
  final double longitude;
  final String? startTime;
  String? endTime;

  _TimelineLocation({
    required this.shortName,
    this.fullAddress,
    required this.latitude,
    required this.longitude,
    this.startTime,
    this.endTime,
  });
}
