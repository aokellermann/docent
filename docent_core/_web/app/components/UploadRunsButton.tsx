import { Button } from '@/components/ui/button';
import { PlusIcon } from 'lucide-react';
import { useRef, useState } from 'react';
import UploadRunsDialog from './UploadRunsDialog';

interface UploadRunsButtonProps {
  onImportSuccess?: (result: {
    status: string;
    message: string;
    num_runs_imported: number;
    filename: string;
    task_id?: string;
    model?: string;
  }) => void;
}

export default function UploadRunsButton({
  onImportSuccess,
}: UploadRunsButtonProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    // Reset the file input so we'll get a new event if the user uploads the same file again
    event.target.value = '';

    setSelectedFile(file);
    setDialogOpen(true);
  };

  const handleDialogClose = () => {
    setDialogOpen(false);
    setSelectedFile(null);
  };

  return (
    <div>
      <input
        ref={fileInputRef}
        type="file"
        accept=".json,.eval"
        onChange={handleFileSelect}
        style={{ display: 'none' }}
      />
      <Button
        variant="outline"
        size="sm"
        onClick={() => fileInputRef.current?.click()}
      >
        <PlusIcon size={16} className="mr-1" />
        Upload Inspect Log
      </Button>

      <UploadRunsDialog
        isOpen={dialogOpen}
        onClose={handleDialogClose}
        file={selectedFile}
        onImportSuccess={onImportSuccess}
      />
    </div>
  );
}
