import { getUser } from '@/app/services/dal';
import { redirect } from 'next/navigation';
import SettingsSidebar from './components/SettingsSidebar';

export default async function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getUser();

  // If user is either not authenticated or anonymous, redirect to login
  if (!user || user.is_anonymous) {
    const encodedRedirect = encodeURIComponent('/settings/api-keys');
    redirect(`/login?redirect=${encodedRedirect}`);
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-6xl">
      <div className="flex gap-8">
        <SettingsSidebar />
        <div className="flex-1">{children}</div>
      </div>
    </div>
  );
}
