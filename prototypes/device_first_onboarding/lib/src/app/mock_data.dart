import 'package:flutter/material.dart';

import '../content.dart';

/// Sample data for the app screens. Everything here is invented; the shapes
/// follow the app's `ServerConversation`, `ActionItem`, `Memory` and `App`
/// models closely enough to review layouts against.

class MockLine {
  const MockLine(this.speaker, this.offset, this.text);

  final String speaker;
  final String offset;
  final String text;
}

class MockConversation {
  const MockConversation({
    required this.id,
    required this.icon,
    required this.title,
    required this.overview,
    required this.start,
    required this.minutes,
    required this.category,
    this.starred = false,
    this.participants = const <String>['You'],
    this.actionItems = const <String>[],
    this.transcript = const <MockLine>[],
  });

  final String id;
  final IconData icon;
  final String title;
  final String overview;
  final DateTime start;
  final int minutes;
  final String category;
  final bool starred;
  final List<String> participants;
  final List<String> actionItems;
  final List<MockLine> transcript;

  String get timeAndLength => '${dfTime(start)} · $minutes min';
}

class MockTask {
  MockTask(this.title, {this.due, this.source, this.done = false});

  final String title;
  final DateTime? due;
  final String? source;
  bool done;
}

class MockMemory {
  const MockMemory(this.category, this.text, this.when);

  final String category;
  final String text;
  final String when;
}

class MockApp {
  const MockApp({
    required this.name,
    required this.icon,
    required this.color,
    required this.category,
    required this.tagline,
    required this.description,
    required this.rating,
    required this.reviews,
    required this.installs,
    this.author = 'Omi',
  });

  final String name;
  final IconData icon;
  final Color color;
  final String category;
  final String tagline;
  final String description;
  final double rating;
  final int reviews;
  final String installs;
  final String author;
}

class MockRecap {
  const MockRecap({
    required this.day,
    required this.headline,
    required this.conversations,
    required this.minutes,
    required this.tasks,
    required this.highlights,
  });

  final DateTime day;
  final String headline;
  final int conversations;
  final int minutes;
  final int tasks;
  final List<String> highlights;
}

/// All sample data, anchored to [today] so dates read naturally.
class MockData {
  MockData(DateTime today) : today = dfDay(today);

  final DateTime today;

  DateTime _at(int daysAgo, int hour, int minute) =>
      today.subtract(Duration(days: daysAgo)).add(Duration(hours: hour, minutes: minute));

  /// Free plan: 300 cloud minutes a month.
  static const int freeMinutes = 300;
  static const int usedMinutes = 214;

  late final List<MockConversation> conversations = <MockConversation>[
    MockConversation(
      id: 'launch',
      icon: Icons.rocket_launch_outlined,
      title: 'Launch timing with Maya',
      overview: 'Agreed to move the launch to Thursday if QA signs off by Wednesday. You will send Maya the revised '
          'deck by Friday; she will brief support on the new onboarding.',
      start: _at(0, 9, 12),
      minutes: 24,
      category: 'Work',
      starred: true,
      participants: const <String>['You', 'Maya'],
      actionItems: const <String>[
        'Send Maya the revised deck',
        'Book a QA review for Wednesday',
        'Draft the launch-day support FAQ',
      ],
      transcript: const <MockLine>[
        MockLine('You', '0:04', 'Can we move the launch to Thursday?'),
        MockLine('Maya', '0:09', 'Thursday works if QA signs off by Wednesday.'),
        MockLine('You', '0:15', "Okay. I'll book the review for Wednesday morning."),
        MockLine('Maya', '0:21', 'And I still need the revised deck before I brief support.'),
        MockLine('You', '0:27', "You'll have it by Friday."),
        MockLine('Maya', '0:31', 'Perfect. Then support gets the new onboarding walkthrough Monday.'),
      ],
    ),
    MockConversation(
      id: 'coffee',
      icon: Icons.coffee_outlined,
      title: 'Coffee with Sam about the seed round',
      overview: 'Sam suggested leading with retention numbers and offered an intro to two angels. Follow up with '
          'the updated metrics one-pager.',
      start: _at(0, 11, 40),
      minutes: 38,
      category: 'Business',
      participants: const <String>['You', 'Sam'],
      actionItems: const <String>['Send Sam the metrics one-pager'],
      transcript: const <MockLine>[
        MockLine('Sam', '0:02', 'Lead with retention. That number is the story.'),
        MockLine('You', '0:07', 'Day-30 is at 41% for paired users.'),
        MockLine('Sam', '0:12', "Send me a one-pager and I'll intro you to two angels."),
      ],
    ),
    MockConversation(
      id: 'standup',
      icon: Icons.extension_outlined,
      title: 'Design standup',
      overview: 'Reviewed the paywall-first onboarding. Winback copy needs a final pass; pairing screens approved.',
      start: _at(0, 14, 5),
      minutes: 15,
      category: 'Work',
      participants: const <String>['You', 'Reid', 'Nik'],
      actionItems: const <String>['Final pass on winback copy'],
    ),
    MockConversation(
      id: 'gym',
      icon: Icons.fitness_center,
      title: 'Training plan with coach',
      overview: 'Three strength days and one long run a week until the half marathon in December.',
      start: _at(1, 7, 30),
      minutes: 12,
      category: 'Health',
      participants: const <String>['You', 'Coach'],
    ),
    MockConversation(
      id: 'pricing',
      icon: Icons.payments_outlined,
      title: 'Pricing review',
      overview: 'Kept yearly at \$269. Testing 3, 7 and 14-day trials with a 30-day winback.',
      start: _at(1, 13, 0),
      minutes: 41,
      category: 'Business',
      starred: true,
      participants: const <String>['You', 'Nik', 'Reid'],
      actionItems: const <String>['Set up the trial-length experiment', 'Write the winback push copy'],
    ),
    MockConversation(
      id: 'dinner',
      icon: Icons.restaurant_outlined,
      title: 'Dinner plans with Jordan',
      overview: 'Saturday at 7:30, the Italian place on Valencia. Jordan is bringing the board game.',
      start: _at(1, 18, 45),
      minutes: 6,
      category: 'Social',
      participants: const <String>['You', 'Jordan'],
    ),
    MockConversation(
      id: 'podcast',
      icon: Icons.headphones_outlined,
      title: 'Podcast notes: memory and attention',
      overview: 'Spaced repetition beats rereading; attention residue lingers about 20 minutes after a switch.',
      start: _at(3, 8, 15),
      minutes: 52,
      category: 'Learning',
    ),
    MockConversation(
      id: 'landlord',
      icon: Icons.key_outlined,
      title: 'Call with the landlord',
      overview: 'Lease renewal at the same rent if signed by the 31st. The plumber comes Tuesday morning.',
      start: _at(4, 16, 20),
      minutes: 9,
      category: 'Personal',
      participants: const <String>['You', 'Dana'],
      actionItems: const <String>['Sign the lease renewal'],
    ),
  ];

  MockConversation conversation(String id) => conversations.firstWhere((c) => c.id == id);

  late final List<MockTask> tasks = <MockTask>[
    MockTask('Sign the lease renewal', due: today.subtract(const Duration(days: 1)), source: 'Call with the landlord'),
    MockTask('Book a QA review for Wednesday', due: today, source: 'Launch timing with Maya'),
    MockTask('Send Sam the metrics one-pager', due: today, source: 'Coffee with Sam'),
    MockTask('Final pass on winback copy', due: today, source: 'Design standup', done: true),
    MockTask('Send Maya the revised deck', due: today.add(const Duration(days: 1)), source: 'Launch timing with Maya'),
    MockTask('Set up the trial-length experiment', due: today.add(const Duration(days: 4)), source: 'Pricing review'),
    MockTask('Draft the launch-day support FAQ', due: today.add(const Duration(days: 6))),
    MockTask('Read "Make It Stick"', source: 'Podcast notes'),
  ];

  static const List<MockMemory> memories = <MockMemory>[
    MockMemory('Work', 'Leads design for the Omi paywall and onboarding', '2d'),
    MockMemory('Work', 'Launch is planned for Thursday, pending QA', 'Today'),
    MockMemory('Interests', 'Training for a half marathon in December', '1d'),
    MockMemory('Interests', 'Enjoys podcasts about memory and learning', '3d'),
    MockMemory('Habits', 'Prefers deep work in the mornings', '1w'),
    MockMemory('People', 'Maya runs support and launch communications', 'Today'),
    MockMemory('People', 'Sam is an advisor on the seed round', 'Today'),
    MockMemory('Lifestyle', 'Has dinner with Jordan most Saturdays', '1d'),
  ];

  static const List<String> memoryCategories = <String>['All', 'Work', 'People', 'Interests', 'Habits', 'Lifestyle'];

  static const List<MockApp> apps = <MockApp>[
    MockApp(
      name: 'Google Calendar',
      icon: Icons.calendar_month,
      color: Color(0xFF4285F4),
      category: 'Productivity',
      tagline: 'Turn plans you mention into events',
      description: 'When you agree on a time in conversation, Omi drafts the event and asks before adding it to your '
          'calendar.',
      rating: 4.7,
      reviews: 1284,
      installs: '48k',
      author: 'Omi',
    ),
    MockApp(
      name: 'Notion',
      icon: Icons.description_outlined,
      color: Color(0xFF111114),
      category: 'Productivity',
      tagline: 'Send summaries to a Notion database',
      description: 'Every conversation summary lands in the Notion database you pick, with action items as a list.',
      rating: 4.6,
      reviews: 932,
      installs: '31k',
    ),
    MockApp(
      name: 'Slack',
      icon: Icons.tag,
      color: Color(0xFF4A154B),
      category: 'Communication',
      tagline: 'Post meeting notes to a channel',
      description: 'Share a conversation summary to any Slack channel in one tap.',
      rating: 4.5,
      reviews: 611,
      installs: '22k',
    ),
    MockApp(
      name: 'Mentor',
      icon: Icons.school_outlined,
      color: Color(0xFFFF8A3D),
      category: 'Personal growth',
      tagline: 'Feedback on how you communicate',
      description: 'After each conversation, Mentor notes one thing you did well and one thing to try next time.',
      rating: 4.8,
      reviews: 2140,
      installs: '67k',
      author: 'Community',
    ),
    MockApp(
      name: 'Todoist',
      icon: Icons.check_circle_outline,
      color: Color(0xFFE44332),
      category: 'Productivity',
      tagline: 'Sync tasks both ways',
      description: 'Action items Omi finds appear in Todoist, and completing them in either app syncs back.',
      rating: 4.4,
      reviews: 388,
      installs: '12k',
    ),
  ];

  late final List<MockRecap> recaps = <MockRecap>[
    MockRecap(
      day: today,
      headline: 'Launch moved to Thursday',
      conversations: 3,
      minutes: 77,
      tasks: 5,
      highlights: const <String>[
        'Launch moves to Thursday if QA signs off by Wednesday.',
        'Sam offered two angel intros once you send the one-pager.',
        'The paywall-first onboarding was approved, pending winback copy.',
      ],
    ),
    MockRecap(
      day: today.subtract(const Duration(days: 1)),
      headline: 'Pricing locked in',
      conversations: 3,
      minutes: 59,
      tasks: 2,
      highlights: const <String>[
        'Yearly stays at \$269 with a 3/7/14-day trial test.',
        'Dinner with Jordan on Saturday at 7:30.',
      ],
    ),
    MockRecap(
      day: today.subtract(const Duration(days: 3)),
      headline: 'Notes on memory',
      conversations: 1,
      minutes: 52,
      tasks: 1,
      highlights: const <String>['Spaced repetition beats rereading.'],
    ),
  ];

  static const List<String> chatSuggestions = <String>[
    'What did I decide today?',
    'What do I still owe people?',
    'What did Omi notice?',
  ];

  /// Canned answers for the chat, keyed by suggestion; anything else gets
  /// the fallback.
  static String answerFor(String question) => switch (question) {
        'What did I decide today?' =>
          'Two decisions today:\n\n• Launch moves to Thursday, as long as QA signs off by Wednesday.\n'
              '• The paywall-first onboarding is approved; the winback copy gets one more pass.',
        'What do I still owe people?' =>
          'Three things:\n\n• Maya: the revised deck, by Friday.\n• Sam: the metrics one-pager.\n'
              '• Your landlord: the signed lease renewal (overdue).',
        'What did Omi notice?' =>
          "You've mentioned the launch in four conversations this week, and you usually schedule deep work "
              'before 11. Wednesday has a QA review at 10. Want me to block 8 to 10 for the deck?',
        _ => "Here's what I found in your conversations from the last week. The launch and the seed round "
            'came up most; ask about either for details.',
      };

  static String sourceFor(String question) => switch (question) {
        'What did I decide today?' => 'Launch timing with Maya · Design standup',
        'What do I still owe people?' => 'Launch timing with Maya · Coffee with Sam · Call with the landlord',
        _ => 'Your conversations',
      };
}
