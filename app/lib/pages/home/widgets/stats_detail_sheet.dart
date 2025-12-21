import 'dart:math';

import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';

class StatsDetailSheet extends StatefulWidget {
  final List<ServerConversation> conversations;
  final int memoriesCount;
  final int wordsCount;

  const StatsDetailSheet({
    super.key,
    required this.conversations,
    required this.memoriesCount,
    required this.wordsCount,
  });

  @override
  State<StatsDetailSheet> createState() => _StatsDetailSheetState();
}

class _StatsDetailSheetState extends State<StatsDetailSheet> {
  late final PageController _pageController;
  late final Map<String, dynamic> _stats;

  // UI Constants
  static const double _cardViewportFraction = 0.52;
  static const double _cardHeight = 320.0;
  static const double _sheetInitialSize = 0.9;

  static const Set<String> _stopwords = {
    // Common articles & determiners
    'the', 'a', 'an', 'this', 'that', 'these', 'those',
    'all', 'any', 'some', 'such', 'both', 'each', 'every',
    'few', 'more', 'most', 'other', 'another', 'much', 'many',

    // Common conjunctions & prepositions
    'and', 'or', 'but', 'nor', 'so', 'yet',
    'to', 'of', 'in', 'for', 'on', 'at', 'by', 'with', 'from',
    'into', 'about', 'after', 'before', 'between', 'through',
    'during', 'above', 'below', 'under', 'over', 'up', 'down',
    'out', 'off', 'against', 'while', 'since', 'until',

    // Common pronouns
    'i', 'me', 'my', 'mine', 'myself',
    'you', 'your', 'yours', 'yourself',
    'he', 'him', 'his', 'himself',
    'she', 'her', 'hers', 'herself',
    'it', 'its', 'itself',
    'we', 'us', 'our', 'ours', 'ourselves',
    'they', 'them', 'their', 'theirs', 'themselves',
    'what', 'which', 'who', 'whom', 'whose',

    // Common verbs (to be, to have, to do)
    'is', 'am', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'having',
    'do', 'does', 'did', 'doing', 'done',

    // Common modal & auxiliary verbs
    'can', 'could', 'may', 'might', 'must',
    'will', 'would', 'shall', 'should',

    // Common adverbs & qualifiers
    'not', 'no', 'yes', 'very', 'too', 'also', 'only', 'just',
    'now', 'then', 'here', 'there', 'when', 'where', 'why', 'how',
    'as', 'than', 'if', 'because',

    // Other high-frequency words
    'get', 'got', 'go', 'going', 'make', 'know', 'think',
    'see', 'come', 'take', 'well', 'back', 'even', 'still',
    'way', 'own', 'say', 'one', 'two'
  };

  @override
  void initState() {
    super.initState();
    // Show roughly two cards at once with a TikTok-style vertical swipe.
    _pageController = PageController(viewportFraction: _cardViewportFraction);
    // Compute stats once during initialization to avoid expensive recalculations on every rebuild
    _stats = _buildStats();
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  DateTime _startOfWeek(DateTime date) {
    final weekday = date.weekday;
    return DateTime(date.year, date.month, date.day).subtract(Duration(days: weekday - 1));
  }

  Map<String, dynamic> _buildStats() {
    final now = DateTime.now();
    final startThisWeek = _startOfWeek(now);
    final startLastWeek = startThisWeek.subtract(const Duration(days: 7));

    int thisWeekConvos = 0;
    int lastWeekConvos = 0;
    int thisWeekWords = 0;
    int lastWeekWords = 0;
    int totalWordsAll = 0;
    double totalDurationSeconds = 0;
    double longestDurationSeconds = 0;
    int maxWordsInConvo = 0;
    final Map<String, int> categoryCounts = {};
    final Map<String, int> categoryCountsThisWeek = {};
    final Map<String, int> categoryCountsLastWeek = {};
    final Map<String, int> dailyCounts = {};
    final Map<String, int> wordFrequency = {};
    final Set<DateTime> convoDays = {};
    final Map<String, int> timeOfDayBuckets = {'Morning': 0, 'Afternoon': 0, 'Evening': 0, 'Night': 0};

    for (int i = 0; i < 7; i++) {
      final day = startThisWeek.add(Duration(days: i));
      dailyCounts[_dayLabel(day)] = 0;
    }

    for (final convo in widget.conversations) {
      final date = convo.createdAt;
      final words = convo.transcriptSegments.fold<int>(0, (sum, seg) {
        final trimmed = seg.text.trim();
        return sum + (trimmed.isEmpty ? 0 : trimmed.split(RegExp(r'\s+')).length);
      });
      totalWordsAll += words;
      maxWordsInConvo = max(maxWordsInConvo, words);

      if (convo.startedAt != null && convo.finishedAt != null) {
        final duration = convo.finishedAt!.difference(convo.startedAt!).inSeconds.toDouble();
        if (duration > 0) {
          totalDurationSeconds += duration;
          longestDurationSeconds = max(longestDurationSeconds, duration);
        }
      }

      if (date.isAfter(startThisWeek.subtract(const Duration(seconds: 1)))) {
        thisWeekConvos += 1;
        thisWeekWords += words;
        final label = _dayLabel(date);
        if (dailyCounts.containsKey(label)) {
          dailyCounts[label] = dailyCounts[label]! + 1;
        }
        convoDays.add(DateTime(date.year, date.month, date.day));
        categoryCountsThisWeek[convo.structured.category] =
            (categoryCountsThisWeek[convo.structured.category] ?? 0) + 1;
      } else if (date.isAfter(startLastWeek.subtract(const Duration(seconds: 1)))) {
        lastWeekConvos += 1;
        lastWeekWords += words;
        categoryCountsLastWeek[convo.structured.category] =
            (categoryCountsLastWeek[convo.structured.category] ?? 0) + 1;
      }

      final category = convo.structured.category;
      categoryCounts[category] = (categoryCounts[category] ?? 0) + 1;

      // Word cloud aggregation
      for (final segment in convo.transcriptSegments) {
        final tokens = segment.text.toLowerCase().split(RegExp(r"[^a-z0-9']+"));
        for (final token in tokens) {
          if (token.length < 3) continue;
          if (_stopwords.contains(token)) continue;
          wordFrequency[token] = (wordFrequency[token] ?? 0) + 1;
        }
      }

      // Time-of-day split (based on conversation start or createdAt fallback)
      final timestamp = convo.startedAt ?? convo.createdAt;
      final hour = timestamp.hour;
      if (hour >= 5 && hour < 12) {
        timeOfDayBuckets['Morning'] = timeOfDayBuckets['Morning']! + 1;
      } else if (hour >= 12 && hour < 17) {
        timeOfDayBuckets['Afternoon'] = timeOfDayBuckets['Afternoon']! + 1;
      } else if (hour >= 17 && hour < 22) {
        timeOfDayBuckets['Evening'] = timeOfDayBuckets['Evening']! + 1;
      } else {
        timeOfDayBuckets['Night'] = timeOfDayBuckets['Night']! + 1;
      }
    }

    final streak = _currentStreak(convoDays);
    final bestDay = dailyCounts.entries.isEmpty
        ? null
        : dailyCounts.entries.reduce((a, b) => a.value >= b.value ? a : b);
    final topWords = wordFrequency.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    return {
      'thisWeekConvos': thisWeekConvos,
      'lastWeekConvos': lastWeekConvos,
      'thisWeekWords': thisWeekWords,
      'lastWeekWords': lastWeekWords,
      'dailyCounts': dailyCounts,
      'topCategories': (categoryCounts.entries.toList()
            ..sort((a, b) => b.value.compareTo(a.value)))
          .take(3)
          .toList(),
      'streak': streak,
      'bestDay': bestDay,
      'topWords': topWords.take(40).toList(),
      'timeOfDayBuckets': timeOfDayBuckets,
      'avgWordsPerConvo': widget.conversations.isEmpty ? 0 : (totalWordsAll / widget.conversations.length),
      'avgWpm': totalDurationSeconds <= 0 ? 0 : totalWordsAll / (totalDurationSeconds / 60),
      'longestDurationMinutes': longestDurationSeconds / 60,
      'maxWordsInConvo': maxWordsInConvo,
      'memoriesPerConvo': widget.conversations.isEmpty ? 0 : widget.memoriesCount / widget.conversations.length,
      'categoryMomentum': _categoryMomentum(categoryCountsThisWeek, categoryCountsLastWeek),
    };
  }

  String _dayLabel(DateTime date) => ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][date.weekday - 1];

  double _trendPercent(int current, int previous) {
    if (previous == 0) return current == 0 ? 0 : 100;
    return ((current - previous) / previous) * 100;
  }

  Color _trendColor(double value) => value >= 0 ? Colors.greenAccent : Colors.redAccent;

  int _currentStreak(Set<DateTime> convoDays) {
    if (convoDays.isEmpty) return 0;
    final today = DateTime.now();
    final normalizedToday = DateTime(today.year, today.month, today.day);
    var streak = 0;
    var cursor = normalizedToday;

    while (convoDays.contains(cursor)) {
      streak += 1;
      cursor = cursor.subtract(const Duration(days: 1));
    }
    return streak;
  }

  List<_CategoryMomentum> _categoryMomentum(Map<String, int> thisWeek, Map<String, int> lastWeek) {
    final Set<String> keys = {...thisWeek.keys, ...lastWeek.keys};
    final List<_CategoryMomentum> result = [];
    for (final key in keys) {
      final current = thisWeek[key] ?? 0;
      final prev = lastWeek[key] ?? 0;
      result.add(_CategoryMomentum(key, current, prev, current - prev));
    }
    result.sort((a, b) => b.delta.compareTo(a.delta));
    return result.take(4).toList();
  }

  Widget _trendChip(String label, int current, int previous) {
    final pct = _trendPercent(current, previous);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          label,
          style: const TextStyle(color: Colors.white70, fontSize: 14),
        ),
        const SizedBox(width: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            color: _trendColor(pct).withOpacity(0.15),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                pct >= 0 ? Icons.trending_up : Icons.trending_down,
                color: _trendColor(pct),
                size: 16,
              ),
              const SizedBox(width: 6),
              Text(
                '${pct >= 0 ? '+' : ''}${pct.toStringAsFixed(1)}%',
                style: TextStyle(
                  color: _trendColor(pct),
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final dailyCounts = _stats['dailyCounts'] as Map<String, int>;
    final topCategories = _stats['topCategories'] as List<MapEntry<String, int>>;
    final streak = _stats['streak'] as int;
    final bestDay = _stats['bestDay'] as MapEntry<String, int>?;
    final topWords = _stats['topWords'] as List<MapEntry<String, int>>;
    final timeOfDayBuckets = _stats['timeOfDayBuckets'] as Map<String, int>;
    final avgWordsPerConvo = _stats['avgWordsPerConvo'] as double;
    final avgWpm = _stats['avgWpm'] as double;
    final longestDurationMinutes = _stats['longestDurationMinutes'] as double;
    final maxWordsInConvo = _stats['maxWordsInConvo'] as int;
    final memoriesPerConvo = _stats['memoriesPerConvo'] as double;
    final categoryMomentum = _stats['categoryMomentum'] as List<_CategoryMomentum>;
    final pages = [
      _buildChartCard(
        title: 'Daily cadence',
        subtitle: 'Conversations per day',
        data: dailyCounts,
      ),
      _buildHeroCard(
        title: 'Words captured',
        subtitle: 'This week total',
        bigNumber: _stats['thisWeekWords'] as int,
        label: 'Words',
        footer: _trendChip('vs last week', _stats['thisWeekWords'] as int, _stats['lastWeekWords'] as int),
      ),
      _buildWordCloudCard(topWords),
      _buildCategoryBreakdownCard(topCategories),
      _buildTimeOfDayCard(timeOfDayBuckets),

      _buildHeroCard(
        title: 'This week',
        subtitle: 'Conversation momentum',
        bigNumber: _stats['thisWeekConvos'] as int,
        label: 'Conversations',
        footer: _trendChip('vs last week', _stats['thisWeekConvos'] as int, _stats['lastWeekConvos'] as int),
      ),
      _buildStreakCard(streak: streak, bestDay: bestDay),



      _buildHeroCard(
        title: 'Memories',
        subtitle: 'Created overall',
        bigNumber: widget.memoriesCount,
        label: 'Memories',
        footer: Text(
          'Total words: ${widget.wordsCount}',
          style: const TextStyle(color: Colors.white60, fontSize: 14),
        ),
      ),
      _buildEfficiencyCard(memoriesPerConvo: memoriesPerConvo, avgWordsPerConvo: avgWordsPerConvo),
      _buildPaceCard(avgWpm: avgWpm, longestMinutes: longestDurationMinutes),
      // _buildPersonalBestCard(maxWords: maxWordsInConvo, longestMinutes: longestDurationMinutes),
      // _buildCategoryMomentumCard(categoryMomentum),
    ];

    final height = MediaQuery.of(context).size.height * 0.9;

    return DraggableScrollableSheet(
      initialChildSize: _sheetInitialSize,
      minChildSize: 0.7,
      maxChildSize: 0.95,
      builder: (context, scrollController) {
        return Container(
          height: height,
          decoration: const BoxDecoration(
            color: Color(0xFF0D0D11),
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Stack(
            children: [
              PageView.builder(
                controller: _pageController,
                scrollDirection: Axis.vertical,
                padEnds: false,
                itemCount: pages.length,
                itemBuilder: (context, index) {
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 60),
                    child: Align(
                      alignment: Alignment.center,
                      child: SizedBox(
                        height: _cardHeight,
                        child: pages[index],
                      ),
                    ),
                  );
                },
              ),
              Positioned(
                top: 12,
                left: 0,
                right: 0,
                child: Center(
                  child: Container(
                    width: 38,
                    height: 4,
                    decoration: BoxDecoration(
                      color: Colors.white24,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ),
              ),
              Positioned(
                top: 16,
                right: 12,
                child: IconButton(
                  icon: const Icon(Icons.close, color: Colors.white70),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ),
              Positioned(
                bottom: 20,
                left: 0,
                right: 0,
                child: Center(
                  child: Icon(
                    Icons.keyboard_arrow_down,
                    color: Colors.white30,
                    size: 24,
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildHeroCard({
    required String title,
    required String subtitle,
    required int bigNumber,
    required String label,
    Widget? footer,
  }) {
    return _glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(color: Colors.white70, fontSize: 15)),
          const SizedBox(height: 2),
          Text(subtitle, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const Spacer(),
          Text(
            bigNumber.toString(),
            style: const TextStyle(color: Colors.white, fontSize: 54, fontWeight: FontWeight.bold, height: 0.95),
          ),
          const SizedBox(height: 6),
          Text(label, style: const TextStyle(color: Colors.white60, fontSize: 14)),
          const SizedBox(height: 8),
          if (footer != null) footer,
        ],
      ),
    );
  }

  Widget _buildChartCard({
    required String title,
    required String subtitle,
    required Map<String, int> data,
  }) {
    final maxValue = data.values.fold<int>(1, max);
    return _glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(color: Colors.white70, fontSize: 15)),
          const SizedBox(height: 2),
          Text(subtitle, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: data.entries
                .map(
                  (e) => Expanded(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          height: maxValue == 0 ? 8 : (e.value / maxValue * 140).clamp(8, 140).toDouble(),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(8),
                            gradient: const LinearGradient(
                              begin: Alignment.bottomCenter,
                              end: Alignment.topCenter,
                              colors: [Color(0xFF7C5DFA), Color(0xFF9D7CFF)],
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(e.key, style: const TextStyle(color: Colors.white60, fontSize: 12)),
                      ],
                    ),
                  ),
                )
                .toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildEfficiencyCard({required double memoriesPerConvo, required double avgWordsPerConvo}) {
    return _glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Efficiency', style: TextStyle(color: Colors.white70, fontSize: 15)),
          const SizedBox(height: 2),
          const Text('Outcome per conversation', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const Spacer(),
          Row(
            children: [
              _miniStat('${memoriesPerConvo.toStringAsFixed(2)}', 'memories / convo'),
              const SizedBox(width: 12),
              _miniStat('${avgWordsPerConvo.toStringAsFixed(0)}', 'avg words / convo'),
            ],
          ),
          const SizedBox(height: 10),
        ],
      ),
    );
  }

  Widget _buildPaceCard({required double avgWpm, required double longestMinutes}) {
    return _glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Pace', style: TextStyle(color: Colors.white70, fontSize: 15)),
          const SizedBox(height: 2),
          const Text('Words per minute', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const Spacer(),
          Row(
            children: [
              _miniStat(avgWpm.isNaN ? '0' : avgWpm.toStringAsFixed(1), 'avg WPM'),
              const SizedBox(width: 12),
              _miniStat('${longestMinutes.toStringAsFixed(1)}m', 'longest session'),
            ],
          ),
          const SizedBox(height: 10),
        ],
      ),
    );
  }

  Widget _buildPersonalBestCard({required int maxWords, required double longestMinutes}) {
    return _glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Personal bests', style: TextStyle(color: Colors.white70, fontSize: 15)),
          const SizedBox(height: 2),
          const Text('Your heaviest sessions', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const Spacer(),
          Row(
            children: [
              _miniStat(maxWords.toString(), 'most words in one'),
              const SizedBox(width: 12),
              _miniStat('${longestMinutes.toStringAsFixed(1)}m', 'longest duration'),
            ],
          ),
          const SizedBox(height: 10),
        ],
      ),
    );
  }

  Widget _buildTimeOfDayCard(Map<String, int> buckets) {
    final maxValue = buckets.values.fold<int>(1, max);
    return _glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Time of day', style: TextStyle(color: Colors.white70, fontSize: 15)),
          const SizedBox(height: 2),
          const Text('When you talk most', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          Row(
            children: buckets.entries.map((e) {
              double height = maxValue == 0 ? 8.0 : (e.value / maxValue * 100.0).clamp(8, 100).toDouble();
              return Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      height: height,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(8),
                        gradient: const LinearGradient(
                          begin: Alignment.bottomCenter,
                          end: Alignment.topCenter,
                          colors: [Color(0xFF56CCF2), Color(0xFF2F80ED)],
                        ),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(e.key, style: const TextStyle(color: Colors.white60, fontSize: 11)),
                    Text(e.value.toString(), style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600)),
                  ],
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildCategoryMomentumCard(List<_CategoryMomentum> items) {
    return _glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Category momentum', style: TextStyle(color: Colors.white70, fontSize: 15)),
          const SizedBox(height: 2),
          const Text('This week vs last week', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          ...items.map((item) {
            final color = _trendColor(item.delta.toDouble());
            final sign = item.delta >= 0 ? '+' : '';
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      item.category[0].toUpperCase() + item.category.substring(1),
                      style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: color.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      '$sign${item.delta}',
                      style: TextStyle(color: color, fontWeight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildCategoryBreakdownCard(List<MapEntry<String, int>> entries) {
    if (entries.isEmpty) {
      return _glass(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: const [
            Text('Top categories', style: TextStyle(color: Colors.white70, fontSize: 15)),
            SizedBox(height: 2),
            Text('Where you talk the most', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
            SizedBox(height: 12),
            Text('No data yet', style: TextStyle(color: Colors.white60)),
          ],
        ),
      );
    }

    final total = entries.fold<int>(0, (sum, e) => sum + e.value);
    final colors = [
      const Color(0xFF9D7CFF),
      const Color(0xFF56CCF2),
      const Color(0xFF7EE0A3),
      const Color(0xFFFFC857),
      const Color(0xFFFF6B6B),
    ];

    return _glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Top categories', style: TextStyle(color: Colors.white70, fontSize: 15)),
          const SizedBox(height: 2),
          const Text('Where you talk the most', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          SizedBox(
            height: 200,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                SizedBox(
                  width: 130,
                  height: 130,
                  child: CustomPaint(
                    painter: _PiePainter(entries: entries, colors: colors, total: total),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ListView.builder(
                    shrinkWrap: true,
                    itemCount: entries.length,
                    itemBuilder: (context, index) {
                      final item = entries[index];
                      final pct = total == 0 ? 0.0 : (item.value / total * 100);
                      final color = colors[index % colors.length];
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Row(
                          children: [
                            Container(
                              width: 12,
                              height: 12,
                              decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3)),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                item.key[0].toUpperCase() + item.key.substring(1),
                                style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
                              ),
                            ),
                            Text(
                              '${item.value} • ${pct.toStringAsFixed(1)}%',
                              style: const TextStyle(color: Colors.white70, fontSize: 13),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _miniStat(String value, String label) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          value,
          style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold, height: 1),
        ),
        const SizedBox(height: 4),
        Text(label, style: const TextStyle(color: Colors.white60, fontSize: 12)),
      ],
    );
  }
  Widget _buildStreakCard({required int streak, required MapEntry<String, int>? bestDay}) {
    final streakLabel = streak == 0 ? 'No streak yet' : '$streak day${streak == 1 ? '' : 's'} streak';
    final bestDayLabel = bestDay == null || bestDay.value == 0 ? 'No top day yet' : '${bestDay.key}: ${bestDay.value} convos';

    return _glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Momentum', style: TextStyle(color: Colors.white70, fontSize: 15)),
          const SizedBox(height: 2),
          const Text('Streaks & best day', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const Spacer(),
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                decoration: BoxDecoration(
                  color: Colors.greenAccent.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.local_fire_department, color: Colors.orangeAccent, size: 20),
                    const SizedBox(width: 8),
                    Text(
                      streakLabel,
                      style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w700),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  bestDayLabel,
                  style: const TextStyle(color: Colors.white70, fontSize: 14),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
        ],
      ),
    );
  }

  Widget _buildWordCloudCard(List<MapEntry<String, int>> topWords) {
    if (topWords.isEmpty) {
      return _glass(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: const [
            Text('Word cloud', style: TextStyle(color: Colors.white70, fontSize: 15)),
            SizedBox(height: 2),
            Text('Most used words', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
            Spacer(),
            Text('Not enough data yet', style: TextStyle(color: Colors.white60)),
          ],
        ),
      );
    }

    final maxCount = topWords.first.value.toDouble().clamp(1, double.infinity);

    return _glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Word cloud', style: TextStyle(color: Colors.white70, fontSize: 15)),
          const SizedBox(height: 2),
          const Text('Most used words', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          Expanded(
            child: SingleChildScrollView(
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: topWords.map((entry) {
                  final weight = entry.value / maxCount;
                  final fontSize = 12 + (weight * 14);
                  final opacity = 0.5 + (weight * 0.5);
                  return Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.08 * opacity),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      entry.key,
                      style: TextStyle(
                        color: Colors.white.withOpacity(opacity),
                        fontSize: fontSize,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildListCard({
    required String title,
    required String subtitle,
    required List<String> entries,
  }) {
    return _glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(color: Colors.white70, fontSize: 15)),
          const SizedBox(height: 2),
          Text(subtitle, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          ...entries.map(
            (e) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                children: [
                  const Icon(Icons.bolt, color: Colors.white54, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      e,
                      style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
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

  Widget _glass({required Widget child}) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.04),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withOpacity(0.08)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.35),
            blurRadius: 24,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      padding: const EdgeInsets.all(18),
      child: child,
    );
  }
}

class _CategoryMomentum {
  final String category;
  final int current;
  final int previous;
  final int delta;

  _CategoryMomentum(this.category, this.current, this.previous, this.delta);
}

class _PiePainter extends CustomPainter {
  final List<MapEntry<String, int>> entries;
  final List<Color> colors;
  final int total;

  _PiePainter({required this.entries, required this.colors, required this.total});

  @override
  void paint(Canvas canvas, Size size) {
    if (total == 0) return;
    final rect = Rect.fromLTWH(0, 0, size.width, size.height);
    double startAngle = -90 * (3.1415926535 / 180); // start at top
    final paint = Paint()..style = PaintingStyle.fill;

    for (int i = 0; i < entries.length; i++) {
      final sweep = (entries[i].value / total) * 2 * 3.1415926535;
      paint.color = colors[i % colors.length];
      canvas.drawArc(rect, startAngle, sweep, true, paint);
      startAngle += sweep;
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}
