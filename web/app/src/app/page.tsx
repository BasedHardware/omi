import { redirect } from 'next/navigation';

export default function HomePage() {
  // Redirect to the apps marketplace as the new landing page
  redirect('/apps');
}
