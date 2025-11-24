'use client';

import SessionReplayBanner from '@/components/SessionReplayBanner';

export default function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <>
      <SessionReplayBanner />
      {children}
    </>
  );
}
