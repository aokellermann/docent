'use client';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useState } from 'react';

interface CommentFormProps {
  initialContent?: string;
  onSave: (content: string) => void;
  onCancel: () => void;
  isEditing?: boolean;
}

export function CommentForm({
  initialContent = '',
  onSave,
  onCancel,
  isEditing = false,
}: CommentFormProps) {
  const [content, setContent] = useState(initialContent);

  const handleSave = () => {
    if (content.trim()) {
      onSave(content.trim());
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSave();
    }
  };

  return (
    <div className="border border-border rounded-lg p-3 space-y-3 bg-background">
      <div className="text-xs font-medium text-muted-foreground">
        {isEditing ? 'Edit Comment' : 'New Comment'}
      </div>

      <Textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Write your comment..."
        className="min-h-[80px] text-xs"
        autoFocus
      />

      <div className="flex gap-2 justify-end">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" onClick={handleSave} disabled={!content.trim()}>
          {isEditing ? 'Save' : 'Add Comment'}
        </Button>
      </div>
    </div>
  );
}
