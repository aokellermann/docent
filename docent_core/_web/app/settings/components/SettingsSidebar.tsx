'use client';

import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  Key,
  Brain,
  Gauge,
  Lock,
  Shield,
  Building2,
  ArrowLeft,
} from 'lucide-react';
import { type LucideIcon } from 'lucide-react';

interface SidebarItem {
  id: string;
  title: string;
  href: string;
  icon: LucideIcon;
}

export const SettingsSidebarItems: Record<string, SidebarItem> = {
  'api-keys': {
    id: 'api-keys',
    title: 'Docent API Keys',
    href: '/settings/api-keys',
    icon: Key,
  },
  'change-password': {
    id: 'change-password',
    title: 'Change Password',
    href: '/settings/change-password',
    icon: Lock,
  },
  'model-providers': {
    id: 'model-providers',
    title: 'Model Providers',
    href: '/settings/model-providers',
    icon: Brain,
  },
  privacy: {
    id: 'privacy',
    title: 'Privacy',
    href: '/settings/privacy',
    icon: Shield,
  },
  usage: {
    id: 'usage',
    title: 'Usage',
    href: '/settings/usage',
    icon: Gauge,
  },
  organizations: {
    id: 'organizations',
    title: 'Organizations',
    href: '/settings/organizations',
    icon: Building2,
  },
};

export default function SettingsSidebar() {
  const router = useRouter();
  const pathname = usePathname();

  return (
    <div className="w-64 space-y-6">
      <Card className="p-4">
        <Link
          href="/"
          className="flex items-center text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back to Collections
        </Link>
        <div>
          <h1 className="text-2xl font-bold mb-2">Settings</h1>
        </div>
        <nav className="space-y-2">
          {Object.values(SettingsSidebarItems).map((item) => {
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
                {item.title}
              </Button>
            );
          })}
        </nav>
      </Card>
    </div>
  );
}
