import { redirect } from 'next/navigation';

export default function Home() {
  // Keep the historical web root routing. The memory-platform landing page
  // lives at /memory-platform so the homepage routing decision can be reviewed
  // separately from adding the new surface.
  redirect('/apps');
}
