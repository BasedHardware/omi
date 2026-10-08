part of 'wrapped_2025_page.dart';

/// A Wrapped result field that does not have the type the cards read. The native projection then
/// keeps the complete Flutter page instead of guessing.
class _MalformedWrapped implements Exception {
  const _MalformedWrapped();
}

/// [value] as a [T], null when absent; any other type is malformed.
T? _wrappedField<T>(Object? value) {
  if (value == null) return null;
  if (value is T) return value as T;
  throw const _MalformedWrapped();
}

/// [map] read as a JSON object, or null when absent.
Map? _wrappedMap(Object? map) => _wrappedField<Map>(map);

String? _wrappedText(Map? map, String key) => _wrappedField<String>(map?[key]);

/// A progress value within 0..1, so real-world data never produces an invalid snapshot.
double _wrappedFraction(num value) => value.isFinite ? value.toDouble().clamp(0.0, 1.0) : 0.0;

/// The native list presentation of Wrapped 2025: one projection per status, with every card's
/// figures and text as rows and each card's share action. The share templates stay Flutter-painted
/// behind the native view through [IosNativeSurface.nativeWrapper].
extension _Wrapped2025Native on _Wrapped2025PageState {
  Widget _buildNative(Widget classic) {
    final l10n = context.l10n;
    final List<NativeSection> sections;
    try {
      sections = _isLoading ? const [] : _nativeSections();
    } on _MalformedWrapped {
      return classic;
    }
    final template = _currentShareTemplate;
    return IosNativeSurface(
      title: l10n.wrapped2025,
      fallback: classic,
      loading: _isLoading,
      toolbar: [
        NativeRow('wrapped_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: sections,
      // Offstage does not paint, so the template is laid out far outside the visible area instead.
      nativeWrapper: (platformView) => Stack(
        fit: StackFit.expand,
        children: [
          platformView,
          if (template != null)
            Positioned(
              left: -10000,
              top: -10000,
              child: RepaintBoundary(key: _shareTemplateKey, child: template),
            ),
        ],
      ),
    );
  }

  List<NativeSection> _nativeSections() {
    final l10n = context.l10n;
    switch (_status) {
      case WrappedStatus.notGenerated:
        return [
          NativeSection('wrapped_start', [
            NativeRow('wrapped_rewind', l10n.wrappedLetsHitRewind, kind: 'label', subtitle: '2025'),
            NativeRow('wrapped_generate', l10n.wrappedGenerateMyWrapped,
                symbol: 'sparkles', action: (_) => _generateWrapped()),
          ]),
        ];
      case WrappedStatus.processing:
        final progress = _wrappedMap(_progress);
        final step = _wrappedText(progress, 'step') ?? l10n.wrappedProcessingDefault;
        final fraction = _wrappedFraction(_wrappedField<num>(progress?['pct']) ?? 0);
        return [
          NativeSection('wrapped_processing', [
            NativeRow('wrapped_creating', l10n.wrappedCreatingYourStory, kind: 'label'),
            NativeRow('wrapped_progress', step,
                kind: 'progress', value: fraction, maximumValue: 1, subtitle: '${(fraction * 100).toInt()}%'),
          ]),
        ];
      case WrappedStatus.error:
        return [
          NativeSection('wrapped_failed', [
            NativeRow('wrapped_error', l10n.wrappedSomethingWentWrong,
                kind: 'label', symbol: 'exclamationmark.triangle', subtitle: _error ?? l10n.wrappedAnErrorOccurred),
            NativeRow('wrapped_retry', l10n.wrappedTryAgain,
                symbol: 'arrow.clockwise', action: (_) => _generateWrapped()),
          ]),
        ];
      case WrappedStatus.done:
        final result = _result;
        if (result == null) {
          return [
            NativeSection('wrapped_empty', [NativeRow('wrapped_no_data', l10n.wrappedNoDataAvailable, kind: 'label')]),
          ];
        }
        return _nativeCards(result);
    }
  }

  /// The thirteen cards, in the classic page order (indices match [_trackCardView]).
  List<NativeSection> _nativeCards(Map<String, dynamic> result) {
    final l10n = context.l10n;
    final numbers = NumberFormat('#,###');

    NativeRow share(String card, void Function() action) =>
        NativeRow('wrapped_share:$card', l10n.wrappedShare, symbol: 'square.and.arrow.up', action: (_) => action());
    // A card's first row reports, through [card], when it scrolls into view, as a page change does.
    NativeRow label(String id, String title, {String subtitle = '', int? card}) => NativeRow(id, title,
        kind: 'label', subtitle: subtitle, onVisible: card == null ? null : (_) => _trackCardView(card));
    NativeSection card(String id, List<NativeRow> rows) => NativeSection('wrapped_card:$id', rows);

    // Year in numbers (1) and the collage (12) read the same totals.
    final totalHours = _wrappedField<num>(result['total_time_hours']) ?? 0.0;
    final totalMinutes = (totalHours.isFinite ? totalHours * 60 : 0).toInt();
    final totalConvs = _wrappedField<int>(result['total_conversations']) ?? 0;
    final daysActive = _wrappedField<int>(result['days_active']) ?? (totalConvs / 3).ceil();
    final percentile = l10n.wrappedTopPercentUser(_calculatePercentile(totalConvs).toString());

    // Top categories (2), with the classic card's computed shares (0% when no breakdown exists).
    final breakdown = <String, int>{};
    for (final item in _wrappedField<List>(result['category_breakdown']) ?? const []) {
      if (item is! Map) continue;
      breakdown[_wrappedText(item, 'category') ?? ''] = _wrappedField<int>(item['count']) ?? 0;
    }
    final topCategories = [
      for (final category in (_wrappedField<List>(result['top_categories']) ?? const []).take(5))
        _wrappedField<String>(category) ?? (throw const _MalformedWrapped()),
    ];
    final total = breakdown.values.fold<int>(0, (sum, value) => sum + value);
    final categories = [
      for (final category in topCategories)
        (
          name: _formatCategory(category),
          percentage: total > 0 ? ((breakdown[category] ?? 0) / total * 100).round() : 0,
        ),
    ];

    // Actions (3).
    final tasks = _wrappedField<int>(result['total_action_items']) ?? 0;
    final completed = _wrappedField<int>(result['completed_action_items']) ?? 0;
    final rateValue = _wrappedField<num>(result['action_items_completion_rate']) ?? 0.0;
    final rate = rateValue.isFinite ? (rateValue * 100).toInt() : 0;

    // Memorable days (4) and best moments (5).
    final days = _wrappedMap(result['memorable_days']);
    final memorable = [
      for (final (key, emoji, labelText, fallbackTitle, fallbackDate) in [
        ('most_fun_day', '🎉', l10n.wrappedMostFunDay, l10n.wrappedAGreatDay, 'January 1'),
        ('most_productive_day', '💪', l10n.wrappedMostProductiveDay, l10n.wrappedGettingItDone, 'June 15'),
        ('most_stressful_day', '😤', l10n.wrappedMostIntenseDay, l10n.wrappedAChallenge, 'December 1'),
      ])
        if (_wrappedMap(days?[key]) case final day?)
          (
            emoji: _wrappedText(day, 'emoji') ?? emoji,
            label: labelText,
            title: _wrappedText(day, 'title') ?? fallbackTitle,
            description: _wrappedText(day, 'description') ?? '',
            date: _wrappedText(day, 'date') ?? fallbackDate,
          ),
    ];
    final funniest = _wrappedMap(result['funniest_event']);
    final cringe = _wrappedMap(result['most_embarrassing_event']);
    final moments = [
      (
        emoji: '😂',
        label: l10n.wrappedFunniestMoment,
        title: _wrappedText(funniest, 'title') ?? l10n.wrappedAHilariousMoment,
        description: _wrappedText(funniest, 'story') ?? l10n.wrappedYouHadFunnyMoments,
        date: _wrappedText(funniest, 'date') ?? 'January 1',
      ),
      (
        emoji: '😅',
        label: l10n.wrappedMostCringeMoment,
        title: _wrappedText(cringe, 'title') ?? l10n.wrappedThatAwkwardMoment,
        description: _wrappedText(cringe, 'story') ?? l10n.wrappedWeveAllBeenThere,
        date: _wrappedText(cringe, 'date') ?? 'January 1',
      ),
    ];
    List<NativeRow> dayRows(String prefix,
            List<({String emoji, String label, String title, String description, String date})> entries) =>
        [
          for (final (i, day) in entries.indexed)
            label('$prefix:$i', '${day.emoji} ${day.title}',
                subtitle: [day.label, day.date, day.description].where((part) => part.isNotEmpty).join('\n')),
        ];

    // Buddies (6).
    final buddies = [
      for (final buddy in _wrappedField<List>(result['top_buddies']) ?? const [])
        _wrappedMap(buddy) ?? (throw const _MalformedWrapped()),
    ];

    // Obsessions (7).
    final obsessions = _wrappedMap(result['obsessions']);
    String obsession(String key) => _capitalizeWords(_wrappedText(obsessions, key) ?? l10n.wrappedNotMentioned);
    final obsessionRows = [
      ('show', '📺', l10n.wrappedShow),
      ('movie', '🎬', l10n.wrappedMovie),
      ('book', '📚', l10n.wrappedBook),
      ('celebrity', '⭐', l10n.wrappedCelebrity),
      ('food', '🍕', l10n.wrappedFood),
    ];

    // Movie recommendations (8).
    final movies = [
      for (final movie in _wrappedField<List>(result['movie_recommendations']) ?? const [])
        _wrappedField<String>(movie) ?? (throw const _MalformedWrapped()),
    ];

    // Struggle (9) and win (10).
    final struggle = _wrappedText(_wrappedMap(result['struggle']), 'title') ?? l10n.wrappedTheHardPart;
    final win = _wrappedText(_wrappedMap(result['personal_win']), 'title') ?? l10n.wrappedPersonalGrowth;

    // Top phrases (11).
    final phrases = [
      for (final phrase in _wrappedField<List>(result['top_phrases']) ?? const [])
        (phrase is Map ? (phrase['phrase'] ?? '') : phrase).toString(),
    ];

    return [
      card('intro', [label('wrapped_intro', '2025', subtitle: l10n.wrappedOmiLifeRecap, card: 0)]),
      card('stats', [
        label('wrapped_minutes', numbers.format(totalMinutes), subtitle: l10n.wrappedMinutes, card: 1),
        label('wrapped_conversations', numbers.format(totalConvs), subtitle: l10n.wrappedConversations),
        label('wrapped_days_active', numbers.format(daysActive), subtitle: l10n.wrappedDaysActive),
        label('wrapped_percentile', percentile),
        share('stats', _shareYearInNumbers),
      ]),
      card('categories', [
        label('wrapped_categories', l10n.wrappedYouTalkedAbout, card: 2),
        for (final (i, category) in categories.indexed)
          NativeRow('wrapped_category:$i', category.name,
              kind: 'progress',
              value: _wrappedFraction(category.percentage / 100),
              maximumValue: 1,
              subtitle: '${category.percentage.clamp(0, 100)}%'),
        share('categories', _shareCategoryChart),
      ]),
      card('actions', [
        label('wrapped_tasks', numbers.format(tasks), subtitle: l10n.wrappedTasksGenerated, card: 3),
        label('wrapped_tasks_completed', numbers.format(completed), subtitle: l10n.wrappedTasksCompleted),
        label('wrapped_completion', '$rate%', subtitle: l10n.wrappedCompletedLabel),
        share('actions', _shareActions),
      ]),
      card('days', [
        label('wrapped_days', l10n.wrappedYourTopDays, card: 4),
        ...dayRows('wrapped_day', memorable),
        share('days', _shareMemorableDays),
      ]),
      card('moments', [
        label('wrapped_moments', '${l10n.wrappedBestHeader} ${l10n.wrappedMomentsHeader}', card: 5),
        ...dayRows('wrapped_moment', moments),
        share('moments', _shareBestMoments),
      ]),
      card('buddies', [
        label('wrapped_buddies', l10n.wrappedMyBuddiesCard, card: 6),
        for (final (i, buddy) in buddies.indexed)
          label('wrapped_buddy:$i',
              '${_wrappedText(buddy, 'emoji') ?? '👋'} ${_wrappedText(buddy, 'name') ?? l10n.wrappedFriend}',
              subtitle: [
                _wrappedText(buddy, 'relationship') ?? l10n.wrappedFriend,
                _wrappedText(buddy, 'context') ?? l10n.wrappedYourBuddy,
              ].where((part) => part.isNotEmpty).join('\n')),
        share('buddies', _shareMyBuddies),
      ]),
      card('obsessions', [
        label('wrapped_obsessions', l10n.wrappedCouldntStopTalkingAbout, card: 7),
        for (final (key, emoji, name) in obsessionRows)
          label('wrapped_obsession:$key', '$emoji ${obsession(key)}', subtitle: name),
        share('obsessions', _shareObsessions),
      ]),
      card('movies', [
        label('wrapped_movies', l10n.wrappedMovieRecs, card: 8),
        for (final (i, movie) in movies.indexed)
          label('wrapped_movie:$i', '🎬 ${_capitalizeWords(movie)}', subtitle: '#${i + 1}'),
        share('movies', _shareMovieRecs),
      ]),
      card('struggle', [
        label('wrapped_struggle', '${l10n.wrappedBiggestHeader} ${l10n.wrappedStruggleHeader}', card: 9),
        label('wrapped_struggle_title', '😤 $struggle', subtitle: l10n.wrappedButYouPushedThroughEmoji),
        share('struggle', _shareStruggle),
      ]),
      card('win', [
        label('wrapped_win', '${l10n.wrappedBiggestHeader} ${l10n.wrappedWinHeader}', card: 10),
        label('wrapped_win_title', '🏆 $win', subtitle: l10n.wrappedYouDidItEmoji),
        share('win', _sharePersonalWin),
      ]),
      card('phrases', [
        label('wrapped_phrases', l10n.wrappedTopFivePhrases, card: 11),
        for (final (i, phrase) in phrases.take(5).indexed) label('wrapped_phrase:$i', phrase, subtitle: '#${i + 1}'),
        share('phrases', _shareTopPhrases),
      ]),
      card('collage', [
        label('wrapped_collage', '2025', subtitle: percentile, card: 12),
        label(
            'wrapped_collage_stats',
            '${numbers.format(totalMinutes)} ${l10n.wrappedMins} · ${numbers.format(totalConvs)} ${l10n.wrappedConvos}'
                ' · ${numbers.format(daysActive)} ${l10n.wrappedDays}'),
        if (buddies.isNotEmpty)
          label('wrapped_collage_buddies', l10n.wrappedBuddiesLabel,
              subtitle: [
                for (final buddy in buddies.take(4))
                  '${_wrappedText(buddy, 'emoji') ?? '👋'} ${_wrappedText(buddy, 'name') ?? ''}',
              ].join('\n')),
        label('wrapped_collage_obsessions', l10n.wrappedObsessionsLabelUpper,
            subtitle: [
              // The collage's own order and placeholder.
              for (final (key, emoji) in [('show', '📺'), ('movie', '🎬'), ('food', '🍕'), ('celebrity', '⭐')])
                '$emoji ${_capitalizeWords(_wrappedText(obsessions, key) ?? '-')}',
            ].join('\n')),
        label('wrapped_collage_struggle', l10n.wrappedStruggleLabelUpper, subtitle: struggle),
        label('wrapped_collage_win', l10n.wrappedWinLabelUpper, subtitle: win),
        if (phrases.isNotEmpty)
          label('wrapped_collage_phrases', l10n.wrappedTopPhrasesLabelUpper, subtitle: phrases.take(3).join('\n')),
        share('collage', _shareFinalCollage),
      ]),
    ];
  }
}
