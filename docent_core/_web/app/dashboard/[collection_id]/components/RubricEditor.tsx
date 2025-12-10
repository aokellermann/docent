'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useState, useEffect, useMemo, useRef } from 'react';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';

import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Badge } from '@/components/ui/badge';

import { type Rubric } from '@/app/store/rubricSlice';
import {
  useGetRubricQuery,
  useGetLatestRubricVersionQuery,
  useGetJudgeModelsQuery,
  rubricApi,
} from '@/app/api/rubricApi';
import { useAppDispatch } from '@/app/store/hooks';
import { cn } from '@/lib/utils';
import ModelPicker from '@/components/ModelPicker';
import RunRubricButton from './RunRubricButton';
import RubricRunDialog from './RubricRunDialog';
import useJobStatus from '@/app/hooks/use-job-status';
import { useLabelSets } from '@/providers/use-label-sets';
import { useHasCollectionWritePermission } from '@/lib/permissions/hooks';
import CodeMirror, { EditorView } from '@uiw/react-codemirror';
import { json as jsonLanguage } from '@codemirror/lang-json';
import { useTheme } from 'next-themes';

export interface RubricVersionNavigatorProps {
  rubric: Rubric | null | undefined;
  maxVersion: number | undefined;
  minVersion: number;
  setRubricVersion?: (version: number) => void;
}

export function RubricVersionNavigator({
  rubric,
  maxVersion,
  minVersion,
  setRubricVersion,
}: RubricVersionNavigatorProps) {
  const handleVersionDecrement = () => {
    if (setRubricVersion && rubric && rubric.version > minVersion) {
      setRubricVersion(rubric.version - 1);
    }
  };

  const handleVersionIncrement = () => {
    if (
      setRubricVersion &&
      rubric &&
      maxVersion !== undefined &&
      rubric.version < maxVersion
    ) {
      setRubricVersion(rubric.version + 1);
    }
  };

  return (
    <div className="flex items-center gap-0.5 bg-secondary rounded border px-1 py-0.5">
      <Button
        size="sm"
        variant="ghost"
        className="h-4 w-4 p-0 hover:bg-background/50"
        onClick={handleVersionDecrement}
        disabled={!rubric || rubric.version <= minVersion}
      >
        <ChevronLeft className="h-2.5 w-2.5" />
      </Button>
      <div className="text-xs font-mono px-1.5 min-w-[2.5rem] text-center">
        {rubric && maxVersion !== undefined
          ? `v${rubric.version}/${maxVersion}`
          : rubric
            ? rubric.version
            : '-'}
      </div>
      <Button
        size="sm"
        variant="ghost"
        className="h-4 w-4 p-0 hover:bg-background/50"
        onClick={handleVersionIncrement}
        disabled={
          !rubric || maxVersion === undefined || rubric.version >= maxVersion
        }
      >
        <ChevronRight className="h-2.5 w-2.5" />
      </Button>
    </div>
  );
}

interface RubricEditorProps {
  collectionId: string;
  rubricId: string;
  rubricVersion: number | null;
  onSave: (rubric: Rubric, clearLabels: boolean) => void;
  onCloseWithoutSave?: () => void;
  editable: boolean;
  onHasUnsavedChangesUpdated?: (hasChanges: boolean) => void;
  shouldConfirmOnSave?: boolean;
}

export default function RubricEditor({
  collectionId,
  rubricId,
  rubricVersion,
  onSave,
  onCloseWithoutSave,
  editable,
  onHasUnsavedChangesUpdated,
  shouldConfirmOnSave,
}: RubricEditorProps) {
  const isDisabled = !editable;

  const dispatch = useAppDispatch();
  const router = useRouter();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const hasOpenedRunDialogRef = useRef(false);

  // Get the remote rubric
  const { data: remoteRubric } = useGetRubricQuery({
    collectionId,
    rubricId,
    version: rubricVersion,
  });

  // Local rubric is for editing
  const [localRubric, setLocalRubric] = useState<Rubric | null>(null);

  const [schemaText, setSchemaText] = useState<string>('');
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [schemaOpen, setSchemaOpen] = useState(false);

  const [isRunDialogOpen, setIsRunDialogOpen] = useState(false);

  const { resolvedTheme } = useTheme();
  const codemirrorExtensions = useMemo(
    () => [jsonLanguage(), EditorView.lineWrapping],
    []
  );

  const hasWritePermission = useHasCollectionWritePermission();

  const { activeLabelSet } = useLabelSets(rubricId);
  const activeLabelSetId = activeLabelSet?.id;
  const {
    // Rubric job status
    rubricJobId,
    rubricJobStatus,

    // Clustering job status
    clusteringJobId,
    centroids,
  } = useJobStatus({
    collectionId,
    rubricId,
    labelSetId: activeLabelSetId ?? null,
  });

  useEffect(() => {
    if (remoteRubric) {
      if (editable) {
        setLocalRubric(remoteRubric);
      }
      setSchemaText(JSON.stringify(remoteRubric.output_schema ?? {}, null, 2));
      setSchemaError(null);
    }
  }, [remoteRubric, editable, setSchemaText, setSchemaError]);

  // Get the latest version number
  const { data: maxVersion } = useGetLatestRubricVersionQuery({
    collectionId,
    rubricId,
  });

  // When the rubric version changes, invalidate the latest rubric version query
  useEffect(() => {
    dispatch(rubricApi.util.invalidateTags([{ type: 'Rubric', id: rubricId }]));
  }, [rubricVersion, rubricId, dispatch]);

  useEffect(() => {
    if (hasOpenedRunDialogRef.current) return;
    const shouldOpenDialog = searchParams.get('openRunDialog') === '1';
    if (shouldOpenDialog) {
      hasOpenedRunDialogRef.current = true;
      setIsRunDialogOpen(true);
      router.replace(pathname);
    }
  }, [searchParams, router, pathname]);

  const { data: availableJudgeModels } = useGetJudgeModelsQuery();

  // The rubric to display is either the local or remote rubric, depending on the editable flag
  const rubric = useMemo(() => {
    return editable ? localRubric : remoteRubric;
  }, [localRubric, remoteRubric, editable]);

  // Helper function to create a new rubric with updates
  const updateRubric = (updates: Partial<Rubric>) => {
    setLocalRubric((prev) => {
      if (!prev) return null;
      return {
        ...prev,
        ...updates,
      };
    });
  };

  // Handler functions for rubric editing
  const handleDescriptionChange = (
    e: React.ChangeEvent<HTMLTextAreaElement>
  ) => {
    if (!editable) return;
    updateRubric({ rubric_text: e.target.value });
  };

  // Don't clear by default
  const handleSave = (clearLabels: boolean = false) => {
    if (rubric) {
      if (maxVersion === undefined) throw new Error('Latest version not found');

      // Validate JSON syntax before saving
      let parsedSchema;
      try {
        parsedSchema = JSON.parse(schemaText);
      } catch (e) {
        setSchemaError(
          `Invalid JSON: ${e instanceof Error ? e.message : 'Unknown error'}`
        );
        return;
      }

      // Clear any existing error
      setSchemaError(null);

      const updatedRubric = {
        ...{
          ...rubric,
          output_schema: parsedSchema,
        },
        // Possibly skips over some versions, if rubric.version < latestVersion
        // TODO(mengk): consider whether this is ok
        version: maxVersion + 1,
      };
      onSave(updatedRubric, clearLabels);
    }
  };

  // Save with confirmation flow
  const [confirmOpen, setConfirmOpen] = useState(false);

  const handleSaveClick = async () => {
    if (!shouldConfirmOnSave || !schemaHasChanges) {
      // Dont clear if schema has not changed
      handleSave(false);
      return;
    }

    setConfirmOpen(true);
  };

  const normalizedRemoteSchema = useMemo(() => {
    return JSON.stringify(remoteRubric?.output_schema ?? {}, null, 2);
  }, [remoteRubric?.output_schema]);

  const schemaHasChanges = useMemo(() => {
    if (!schemaText || !remoteRubric) return false;
    return schemaText !== normalizedRemoteSchema;
  }, [schemaText, normalizedRemoteSchema, remoteRubric]);

  const schemaPropertyCount = useMemo(() => {
    try {
      const parsed = JSON.parse(schemaText || '{}');
      if (
        !parsed ||
        typeof parsed !== 'object' ||
        Array.isArray(parsed) ||
        typeof parsed.properties !== 'object' ||
        parsed.properties === null
      ) {
        return 0;
      }
      return Object.keys(parsed.properties).length;
    } catch (error) {
      return 0;
    }
  }, [schemaText]);

  const hasChanges = useMemo(() => {
    if (!editable || !rubric || !remoteRubric) return false;
    return (
      rubric.rubric_text !== remoteRubric.rubric_text ||
      JSON.stringify(rubric.judge_model) !==
        JSON.stringify(remoteRubric.judge_model) ||
      schemaHasChanges
    );
  }, [rubric, remoteRubric, editable, schemaHasChanges]);
  useEffect(() => {
    if (onHasUnsavedChangesUpdated) {
      onHasUnsavedChangesUpdated(hasChanges);
    }
  }, [hasChanges, onHasUnsavedChangesUpdated]);

  return (
    <div className="space-y-2">
      <div className="space-y-2 relative">
        {/* Rubric Text */}
        <div className="space-y-1">
          <div className="relative overflow-hidden rounded-md border bg-background focus-within:ring-1 focus-within:ring-ring">
            <Textarea
              className={cn(
                'h-[30vh] max-h-[50vh] resize-y border-0 p-2 shadow-none focus-visible:ring-0 text-sm custom-scrollbar'
              )}
              placeholder="Enter a high-level description of what this rubric evaluates..."
              value={rubric?.rubric_text || ''}
              onChange={handleDescriptionChange}
              disabled={isDisabled}
              style={isDisabled ? { opacity: 1, color: 'inherit' } : undefined}
            />

            {/* Save Button */}
            {hasChanges && (
              <div className="flex absolute bottom-2 right-2 justify-end gap-2">
                {onCloseWithoutSave && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      // Reset local changes to the latest remote rubric
                      if (remoteRubric) {
                        setLocalRubric(remoteRubric);
                        setSchemaText(
                          JSON.stringify(
                            remoteRubric.output_schema ?? {},
                            null,
                            2
                          )
                        );
                        setSchemaError(null);
                      }
                      // Clear any inline edit state
                      onCloseWithoutSave();
                    }}
                  >
                    Cancel
                  </Button>
                )}
                {shouldConfirmOnSave && schemaHasChanges ? (
                  <Popover open={confirmOpen} onOpenChange={setConfirmOpen}>
                    <PopoverTrigger asChild>
                      <Button
                        size="sm"
                        disabled={isDisabled}
                        onClick={handleSaveClick}
                        className="gap-1.5"
                      >
                        Save
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-80 p-3 space-y-2" align="end">
                      <div className="text-sm font-medium">
                        You have existing labels
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Versioning the rubric with a new schema will clear all
                        existing labels.
                      </div>
                      <div className="flex justify-end gap-2 pt-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setConfirmOpen(false)}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setConfirmOpen(false);
                            // Clear if schema has changed
                            handleSave(true);
                          }}
                        >
                          Save
                        </Button>
                      </div>
                    </PopoverContent>
                  </Popover>
                ) : (
                  <Button
                    size="sm"
                    disabled={isDisabled}
                    onClick={handleSaveClick}
                    className="gap-1.5"
                  >
                    Save
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      {/* Output Schema and Actions */}
      <div className="flex flex-row gap-1">
        <Popover open={schemaOpen} onOpenChange={setSchemaOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cn(
                'grow inline-flex items-center justify-start transition-colors rounded-md h-7 px-2 py-1.5 border bg-background shadow-sm whitespace-nowrap overflow-hidden basis-32',
                editable ? 'hover:bg-accent' : 'cursor-default'
              )}
              onClick={() => setSchemaOpen(!schemaOpen)}
              aria-expanded={schemaOpen}
            >
              <ChevronRight
                className={cn(
                  'h-3 w-3 transition-transform flex-shrink-0',
                  schemaOpen ? 'rotate-90' : ''
                )}
              />
              <div className="flex gap-2 items-center">
                <span className="text-xs text-muted-foreground">
                  Output Schema
                </span>
                {schemaPropertyCount > 0 && (
                  <Badge variant="secondary" className="text-xs">
                    {schemaPropertyCount}
                  </Badge>
                )}
              </div>
            </button>
          </PopoverTrigger>

          <PopoverContent
            className="w-[600px] p-0"
            align="start"
            side="bottom"
            sideOffset={4}
          >
            <div className="flex flex-col max-h-[400px]">
              <div className="flex-1 overflow-y-auto custom-scrollbar">
                <CodeMirror
                  value={schemaText}
                  height="auto"
                  theme={resolvedTheme === 'dark' ? 'dark' : 'light'}
                  extensions={codemirrorExtensions}
                  onChange={(value) => setSchemaText(value)}
                  basicSetup={{
                    lineNumbers: false,
                    highlightActiveLine: true,
                    foldGutter: false,
                  }}
                  readOnly={!editable}
                />
              </div>

              {schemaError && (
                <div className="text-xs p-2 text-red-text border-t bg-red-bg/50">
                  {schemaError}
                </div>
              )}
            </div>
          </PopoverContent>
        </Popover>

        {rubric && (
          <ModelPicker
            selectedModel={rubric.judge_model}
            availableModels={availableJudgeModels}
            onChange={(jm) => {
              if (!editable) return;
              updateRubric({ judge_model: jm });
            }}
            className="basis-32"
            shortenName
          />
        )}

        {!clusteringJobId && hasWritePermission && centroids.length === 0 && (
          <RunRubricButton
            collectionId={collectionId}
            rubricId={rubricId}
            rubricJobId={rubricJobId}
            rubricJobStatus={rubricJobStatus}
            hasUnsavedChanges={hasChanges}
            onClick={() => setIsRunDialogOpen(true)}
          />
        )}

        <RubricRunDialog
          isOpen={isRunDialogOpen}
          onClose={() => setIsRunDialogOpen(false)}
          collectionId={collectionId}
          rubricId={rubricId}
        />
      </div>
    </div>
  );
}
