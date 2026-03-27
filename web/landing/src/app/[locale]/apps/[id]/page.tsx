import { AppDetailContent } from './app-detail-content';

interface Props {
  params: { id: string; locale: string };
}

export default function AppDetailPage({ params }: Props) {
  return <AppDetailContent appId={params.id} />;
}
