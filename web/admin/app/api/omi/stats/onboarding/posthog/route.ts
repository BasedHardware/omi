import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
export const dynamic = 'force-dynamic';

const STEP_DEFINITIONS = [
  { key: 'name', label: 'Name', eventNames: ['Onboarding Step Name Completed'] },
  { key: 'language', label: 'Language', eventNames: ['Onboarding Step Language Completed'] },
  { key: 'trust', label: 'Trust', eventNames: ['Onboarding Step Trust Completed'] },
  {
    key: 'screen_recording',
    label: 'Screen Recording',
    eventNames: [
      'Onboarding Step ScreenRecording Completed',
      'Onboarding Step ScreenRecording_Skipped Completed',
    ],
  },
  {
    key: 'full_disk_access',
    label: 'Full Disk Access',
    eventNames: [
      'Onboarding Step FullDiskAccess Completed',
      'Onboarding Step FullDiskAccess_Skipped Completed',
    ],
  },
  {
    key: 'file_scan',
    label: 'File Scan',
    eventNames: ['Onboarding Step FileScan Completed', 'Onboarding Step FileScan_Skipped Completed'],
  },
  {
    key: 'microphone',
    label: 'Microphone',
    eventNames: ['Onboarding Step Microphone Completed', 'Onboarding Step Microphone_Skipped Completed'],
  },
  {
    key: 'notifications',
    label: 'Notifications',
    eventNames: [
      'Onboarding Step Notifications Completed',
      'Onboarding Step Notifications_Skipped Completed',
    ],
  },
  {
    key: 'accessibility',
    label: 'Accessibility',
    eventNames: [
      'Onboarding Step Accessibility Completed',
      'Onboarding Step Accessibility_Skipped Completed',
    ],
  },
  {
    key: 'automation',
    label: 'Automation',
    eventNames: ['Onboarding Step Automation Completed', 'Onboarding Step Automation_Skipped Completed'],
  },
  {
    key: 'floating_bar_shortcut',
    label: 'Floating Bar Shortcut',
    eventNames: [
      'Onboarding Step FloatingBarShortcut Completed',
      'Onboarding Step FloatingBarShortcut_Skipped Completed',
    ],
  },
  {
    key: 'floating_bar',
    label: 'Floating Bar',
    eventNames: ['Onboarding Step FloatingBar Completed', 'Onboarding Step FloatingBar_Skipped Completed'],
  },
  {
    key: 'voice_shortcut',
    label: 'Voice Shortcut',
    eventNames: ['Onboarding Step VoiceShortcut Completed', 'Onboarding Step VoiceShortcut_Skipped Completed'],
  },
  {
    key: 'voice_demo',
    label: 'Voice Demo',
    eventNames: ['Onboarding Step VoiceDemo Completed', 'Onboarding Step VoiceDemo_Skipped Completed'],
  },
  { key: 'research', label: 'Research', eventNames: ['Onboarding Step Research Completed'] },
  { key: 'goal', label: 'Goal', eventNames: ['Onboarding Step Goal Completed'] },
  {
    key: 'tasks',
    label: 'Tasks',
    eventNames: ['Onboarding Step Tasks Completed', 'Onboarding Step Tasks_Skipped Completed'],
  },
  { key: 'completed', label: 'Completed', eventNames: ['Onboarding Completed'] },
];

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
    const projectId = process.env.POSTHOG_PROJECT_ID;
    const host = (process.env.POSTHOG_HOST || 'https://us.posthog.com').replace(/\/$/, '');

    if (!apiKey || !projectId) {
      return NextResponse.json({ error: 'PostHog credentials not configured' }, { status: 500 });
    }

    const searchParams = request.nextUrl.searchParams;
    const days = parseInt(searchParams.get('days') || '30', 10);

    const eventNames = STEP_DEFINITIONS.flatMap((step) => step.eventNames);
    const escapedEventNames = eventNames.map((name) => `'${name.replace(/'/g, "\\'")}'`).join(', ');
    const url = `${host}/api/projects/${projectId}/query/`;

    const body = {
      query: {
        kind: 'HogQLQuery',
        query: `
          WITH entrant_actors AS (
            SELECT actor_id
            FROM (
              SELECT
                COALESCE(person_id, distinct_id) AS actor_id,
                argMin(event, timestamp) AS first_event_name,
                min(timestamp) AS first_event_at
              FROM events
              WHERE event IN (${escapedEventNames})
                AND properties.$os = 'macOS'
              GROUP BY actor_id
            )
            WHERE first_event_name = 'Onboarding Step Name Completed'
              AND first_event_at >= now() - INTERVAL ${days} DAY
          )
          SELECT
            COALESCE(person_id, distinct_id) AS actor_id,
            event
          FROM events
          WHERE event IN (${escapedEventNames})
            AND properties.$os = 'macOS'
            AND COALESCE(person_id, distinct_id) IN (SELECT actor_id FROM entrant_actors)
          GROUP BY actor_id, event
          LIMIT 10000
        `,
      },
    };

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text();
      console.error('PostHog onboarding API error:', response.status, text);
      return NextResponse.json({ error: `PostHog API error: ${response.status}` }, { status: 502 });
    }

    const raw = await response.json();
    const rows = Array.isArray(raw.results) ? raw.results : [];

    const eventToStepIndex = new Map<string, number>();
    STEP_DEFINITIONS.forEach((step, index) => {
      step.eventNames.forEach((eventName) => eventToStepIndex.set(eventName, index));
    });

    const actorSteps = new Map<string, Set<number>>();

    for (const row of rows) {
      const actorId = row[0];
      const eventName = row[1];
      const stepIndex = eventToStepIndex.get(eventName);
      if (!actorId || stepIndex == null) continue;

      const completed = actorSteps.get(actorId) ?? new Set<number>();
      completed.add(stepIndex);
      actorSteps.set(actorId, completed);
    }

    const usersByStep = new Array<number>(STEP_DEFINITIONS.length).fill(0);

    for (const completedSteps of Array.from(actorSteps.values())) {
      let furthestSequentialStep = -1;
      for (let stepIndex = 0; stepIndex < STEP_DEFINITIONS.length; stepIndex++) {
        if (!completedSteps.has(stepIndex)) break;
        furthestSequentialStep = stepIndex;
      }

      for (let stepIndex = 0; stepIndex <= furthestSequentialStep; stepIndex++) {
        usersByStep[stepIndex] += 1;
      }
    }

    const totalUsers = usersByStep[0] ?? 0;
    const steps = STEP_DEFINITIONS.map((step, index) => ({
      key: step.key,
      label: step.label,
      users: usersByStep[index],
      completionRate:
        totalUsers > 0 ? Math.round((usersByStep[index] / totalUsers) * 10000) / 100 : 0,
    }));

    return NextResponse.json({
      days,
      totalUsers,
      methodology:
        'First-ever entrants into the current macOS onboarding flow, using users whose earliest recorded onboarding event is Name inside the selected window.',
      steps,
    });
  } catch (error) {
    console.error('Error fetching PostHog onboarding funnel:', error);
    return NextResponse.json(
      { error: 'Failed to fetch PostHog onboarding funnel data' },
      { status: 500 }
    );
  }
}
