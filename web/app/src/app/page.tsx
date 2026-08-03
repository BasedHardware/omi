import { redirect } from '@tschk/moonshine-server';

export default function HomePage() {
  // Redirect to the login page as the home page
  redirect('/login');
}
