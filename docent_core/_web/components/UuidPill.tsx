import { toast } from '@/hooks/use-toast';
import { copyToClipboard } from '@/lib/utils';
import { Copy } from 'lucide-react';

export default function UuidPill({ uuid }: { uuid?: string }) {
  if (!uuid) return null;

  const onClick = async () => {
    const success = await copyToClipboard(uuid);
    if (success) {
      toast({
        title: 'Copied to clipboard',
        description: 'Full UUID copied to clipboard',
        variant: 'default',
      });
    } else {
      toast({
        title: 'Failed to copy',
        description: 'Could not copy to clipboard',
        variant: 'destructive',
      });
    }
  };

  return (
    <span
      className="inline-flex items-center h-7 gap-x-1 pl-1 pr-0.5 py-0.5 rounded-md text-xs font-mono text-muted-foreground bg-muted border border-border cursor-pointer hover:bg-accent transition-colors"
      onClick={onClick}
      title="Click to copy full UUID"
    >
      <Copy className="h-3 w-3" />
      {uuid}
    </span>
  );
}
