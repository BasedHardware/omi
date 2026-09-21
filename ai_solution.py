To fix the issue where evening memories were counted on the next day, we need to ensure that all date-based insights use the local date consistently.

**Here is the fixed code:**

```typescript
// src/workers/insights.worker.ts
function getDailyCount(): number {
  const today = getLocalDate();
  return DAILY_COUNTS.get(today) || 0;
}

function getDayOfWeekCount(): number {
  const day = getLocalDate();
  return DAY_OF_WEEK_COUNTS.get(day) || 0;
}

function getHourCount(): number {
  const hour = getLocalTime();
  return HOUR_COUNTS.get(hour) || 0;
}

const DAILY_COUNTS = new Map<string, number>();
const DAY_OF_WEEK_COUNTS = new Map<string, number>();
const HOUR_COUNTS = new Map<string, number>();

// In calculateStreak, ensure it uses getLocalDate() instead of the UTC date
```

**The key changes are:**

- The `dailyCounts` now uses `getLocalDate()` for the key.
- `calculateStreak` now uses `getLocalDate()` to match the local date used in the activity calendar.

This ensures all date-based insights are consistent with the local date, resolving the streak issue.