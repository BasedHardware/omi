import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';

// Entirely fictional. No account reads, transcripts, names or user media.
final fixtureDay = DateTime(2026, 11, 9, 9, 10);

ServerConversation recording(String id, String title, String gist, int minutes, {bool noise = false}) {
  final at = fixtureDay.add(Duration(minutes: minutes));
  return ServerConversation(
    id: id,
    createdAt: at,
    startedAt: at,
    finishedAt: at.add(Duration(minutes: noise ? 1 : 22)),
    homeStep: noise ? 'noise' : 'ready',
    structured: Structured(title, gist, emoji: '💬', titleProvenance: noise ? 'server_minimum' : null),
  );
}

Episode fixture(String state) {
  final few = state == 'few-members';
  final long = state == 'long-summary';
  final noisy = state == 'many-noisy';
  final members = [
    recording('planning', 'Planning the garden workshop', 'A smaller group, more time for hands-on practice.', 0),
    if (!few)
      recording('supplies', 'Supplies and room layout', 'Reuse the trays and put the worktables by the windows.', 85),
    if (!few && !noisy)
      recording('invite', 'An invitation for the neighborhood',
          'Keep the invitation simple and welcoming to beginners.', long ? 165 : 205),
    if (long) recording('rain', 'Making a plan for rain', 'Move indoors if the courtyard is wet on Saturday.', 205),
    for (var i = 0; i < (noisy ? 8 : (few ? 0 : 2)); i++)
      recording('noise-$i', i.isEven ? 'Recording · 10:${20 + i}' : 'Thank you.', '', 30 + i * 12, noise: true),
  ]..sort((a, b) => a.createdAt.compareTo(b.createdAt));
  final moments = [
    EpisodeMoment(
      id: 'plan',
      conversationId: 'planning',
      startedAt: fixtureDay,
      endedAt: fixtureDay.add(const Duration(minutes: 22)),
      heading: 'A workshop for first-time gardeners',
      points: [
        const EpisodePoint('Keep the group small so everyone can plant a tray.',
            details: ['Start with herbs and salad greens; leave the fruit trees for a later session.']),
        if (long)
          const EpisodePoint('Give the first half hour to a demonstration, then let people work in pairs.',
              details: ['Keep a spare tray at each table so late arrivals can join without interrupting.']),
      ],
    ),
    if (!few)
      EpisodeMoment(
        id: 'space',
        conversationId: 'supplies',
        startedAt: fixtureDay.add(const Duration(minutes: 85)),
        endedAt: fixtureDay.add(const Duration(minutes: 107)),
        heading: 'Use what the community room has',
        points: [
          const EpisodePoint('Reuse the seed trays and set up beside the windows.'),
          if (long)
            const EpisodePoint('Keep a clear path between the worktables and the door.',
                details: ['Put soil and tools on a separate table so people can collect supplies at their own pace.']),
        ],
      ),
    if (long) ...[
      EpisodeMoment(
        id: 'welcome',
        conversationId: 'invite',
        startedAt: fixtureDay.add(const Duration(minutes: 165)),
        endedAt: fixtureDay.add(const Duration(minutes: 187)),
        heading: 'Make the invitation feel welcoming',
        points: const [
          EpisodePoint('Say explicitly that no gardening experience or equipment is needed.',
              details: ['People can bring a container from home, but spare containers will be available.']),
          EpisodePoint('Share the invitation at the library and on the community noticeboard.'),
        ],
      ),
      EpisodeMoment(
        id: 'weather',
        conversationId: 'rain',
        startedAt: fixtureDay.add(const Duration(minutes: 205)),
        endedAt: fixtureDay.add(const Duration(minutes: 227)),
        heading: 'An indoor plan if it rains',
        points: const [
          EpisodePoint('Use the community room if the courtyard is wet.',
              details: ['Bring washable table covers and a broom; keep the outdoor entrance clear.']),
          EpisodePoint('Send a location reminder the evening before the workshop.'),
        ],
      ),
    ],
  ];
  return Episode(
    id: 'synthetic-$state',
    live: false,
    title: few ? 'A plan for the garden workshop' : 'Bringing the garden workshop together',
    startedAt: fixtureDay,
    lastActivityAt: fixtureDay.add(Duration(minutes: few ? 22 : 227)),
    lede: few
        ? 'The first workshop will focus on herbs and salad greens, with a small group and plenty of time to practice.'
        : 'The garden workshop is taking shape: a small, hands-on session for beginners, using supplies already in the community room.',
    bullets: const ['A small workshop for first-time gardeners.'],
    followUps: [
      'Check the seed trays before Saturday.',
      if (!few) 'Share the invitation at the library.',
      if (long) 'Send the final location the evening before.',
    ],
    members: members,
    conversationIds: members.map((m) => m.id).toList(),
    moments: moments,
  );
}
