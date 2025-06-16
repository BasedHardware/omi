import { Metadata } from 'next';
import UserContent from './content';

export const metadata: Metadata = {
  title: 'Omi - User Profile',
  description: 'View user profile and personas',
}

type Props = {
  params: Promise<{ username: string }>
}

export default async function UsernamePage({ params }: Props) {
  const { username } = await params;
  return <UserContent username={username} />
}
