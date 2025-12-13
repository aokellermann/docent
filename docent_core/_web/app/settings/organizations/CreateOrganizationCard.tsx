'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { toast } from '@/hooks/use-toast';
import { useCreateOrganizationMutation } from '@/app/api/orgApi';
import { getRtkQueryErrorMessage } from '@/lib/rtkQueryError';

export default function CreateOrganizationCard() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [createOrg, { isLoading }] = useCreateOrganizationMutation();

  const onCreate = async () => {
    const trimmedName = name.trim();
    if (!trimmedName) return;
    try {
      const org = await createOrg({
        name: trimmedName,
        description: description.trim() || undefined,
      }).unwrap();
      toast({ title: 'Organization created', description: org.name });
      router.push(`/settings/organizations/${org.id}`);
      router.refresh();
    } catch (err: unknown) {
      const parsed = getRtkQueryErrorMessage(
        err,
        'Failed to create organization.'
      );
      toast({
        title: 'Error',
        description: parsed.message,
        variant: 'destructive',
      });
    }
  };

  return (
    <Card className="p-3 space-y-3">
      <div className="space-y-1">
        <div className="font-medium">Create organization</div>
        <div className="text-sm text-muted-foreground">
          Create a new organization and become its first admin.
        </div>
      </div>

      <div className="space-y-2">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Organization name"
          className="h-7 text-xs"
        />
        <Input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)"
          className="h-7 text-xs"
        />
        <div>
          <Button
            size="sm"
            className="h-7"
            disabled={!name.trim() || isLoading}
            onClick={onCreate}
          >
            Create
          </Button>
        </div>
      </div>
    </Card>
  );
}
