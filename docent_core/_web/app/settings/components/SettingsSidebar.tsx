'use client';

import { usePathname, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Key, Brain, Gauge } from 'lucide-react';

interface SidebarItem {
  id: string;
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const sidebarItems: SidebarItem[] = [
  {
    id: 'api-keys',
    label: 'Docent API Keys',
    href: '/settings/api-keys',
    icon: Key,
  },
  {
    id: 'model-providers',
    label: 'Model Providers',
    href: '/settings/model-providers',
    icon: Brain,
  },
  {
    id: 'usage',
    label: 'Usage',
    href: '/settings/usage',
    icon: Gauge,
  },
];

export default function SettingsSidebar() {
  const router = useRouter();
  const pathname = usePathname();

  return (
    <div className="w-64 space-y-6">
      <Card className="p-4">
        <div>
          <h1 className="text-2xl font-bold mb-2">Settings</h1>
        </div>
        <nav className="space-y-2">
          {sidebarItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;

            return (
              <Button
                key={item.id}
                variant={isActive ? 'default' : 'ghost'}
                className={'w-full justify-start'}
                onClick={() => router.push(item.href)}
              >
                <Icon className="mr-2 h-4 w-4" />
                {item.label}
              </Button>
            );
          })}
        </nav>
      </Card>
    </div>
  );
}
