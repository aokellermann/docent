'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { X, Loader2, ChevronDown, Copy, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { getNextForkName } from '@/lib/investigatorUtils';
import { useListAvailableModelsMutation } from '@/app/api/investigatorApi';
import { useDebounce } from '@/hooks/use-debounce';

type BackendType = 'openai_compatible' | 'anthropic_compatible';

interface OpenAIBackendData {
  backend_type: 'openai_compatible';
  name: string;
  provider: string;
  model: string;
  api_key?: string;
  base_url?: string;
}

interface AnthropicBackendData {
  backend_type: 'anthropic_compatible';
  name: string;
  provider: string;
  model: string;
  max_tokens: number;
  thinking_type?: 'enabled' | 'disabled';
  thinking_budget_tokens?: number;
  api_key?: string;
  base_url?: string;
}

type BackendData = OpenAIBackendData | AnthropicBackendData;

interface BackendEditorProps {
  initialValue?: Partial<BackendData>;
  readOnly?: boolean;
  onSave?: (data: BackendData) => void;
  onFork?: (data: BackendData) => void;
  onDelete?: () => void;
  onCancel?: () => void;
  onClose?: () => void;
}

// Provider options for OpenAI-compatible backends
const OPENAI_COMPATIBLE_PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'google', label: 'Google' },
  { value: 'openrouter', label: 'OpenRouter' },
  { value: 'custom', label: 'Custom' },
];

// Provider options for Anthropic-compatible backends (only anthropic is supported)
const ANTHROPIC_COMPATIBLE_PROVIDER_OPTIONS = [
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'custom', label: 'Custom' },
];

// Base URLs for OpenAI-compatible backends
const OPENAI_COMPATIBLE_BASE_URLS: Record<string, string> = {
  openai: 'https://api.openai.com/v1/',
  google: 'https://generativelanguage.googleapis.com/v1beta/openai/',
  openrouter: 'https://openrouter.ai/api/v1',
};

// Base URLs for Anthropic-compatible backends
const ANTHROPIC_COMPATIBLE_BASE_URLS: Record<string, string> = {
  anthropic: 'https://api.anthropic.com',
};

// Common models for each provider (fallback if API call fails)
const FALLBACK_MODELS: Record<string, string[]> = {
  openai: [
    'gpt-4.1',
    'gpt-4.1-mini',
    'gpt-5-mini',
    'gpt-5-chat-latest',
    'gpt-5',
  ],
  anthropic: [
    'claude-sonnet-4-20250514',
    'claude-opus-4-1-20250805',
    'claude-3-5-haiku-20241022',
  ],
  google: ['gemini-2.5-flash', 'gemini-2.5-pro'],
  openrouter: [
    'openai/gpt-4o',
    'anthropic/claude-3.5-sonnet',
    'meta-llama/llama-3.1-8b-instruct',
  ],
  custom: [],
};

export default function BackendEditor({
  initialValue,
  readOnly = false,
  onSave,
  onFork,
  onDelete,
  onCancel,
  onClose,
}: BackendEditorProps) {
  const [backendType, setBackendType] = useState<BackendType>(
    initialValue?.backend_type || 'openai_compatible'
  );
  const [name, setName] = useState(initialValue?.name || '');
  const [provider, setProvider] = useState(initialValue?.provider || 'openai');
  const [model, setModel] = useState(initialValue?.model || '');
  const [apiKey, setApiKey] = useState(initialValue?.api_key || '');
  const [baseUrl, setBaseUrl] = useState(initialValue?.base_url || '');

  // Anthropic-specific fields
  const [maxTokens, setMaxTokens] = useState(
    (initialValue as Partial<AnthropicBackendData>)?.max_tokens || 4000
  );
  const [thinkingType, setThinkingType] = useState<
    'enabled' | 'disabled' | undefined
  >((initialValue as Partial<AnthropicBackendData>)?.thinking_type);
  const [thinkingBudgetTokens, setThinkingBudgetTokens] = useState(
    (initialValue as Partial<AnthropicBackendData>)?.thinking_budget_tokens ||
      2000
  );

  const [modelOpen, setModelOpen] = useState(false);
  const [modelSearch, setModelSearch] = useState('');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [syncNameWithModel, setSyncNameWithModel] = useState(
    !initialValue && !readOnly
  ); // Default to true for new configs
  const [errors, setErrors] = useState<{
    name?: string;
    model?: string;
    base_url?: string;
    max_tokens?: string;
    thinking_budget_tokens?: string;
  }>({});
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const handleClose = () => {
    if (onClose) {
      onClose();
    } else if (onCancel) {
      onCancel();
    }
  };

  const debouncedModelSearch = useDebounce(modelSearch, 300);
  const [listModels, { isLoading: isLoadingModels }] =
    useListAvailableModelsMutation();

  // Update base URL when provider or backend type changes
  useEffect(() => {
    if (provider !== 'custom') {
      if (backendType === 'anthropic_compatible') {
        setBaseUrl(ANTHROPIC_COMPATIBLE_BASE_URLS[provider] || '');
      } else {
        setBaseUrl(OPENAI_COMPATIBLE_BASE_URLS[provider] || '');
      }
    }
  }, [provider, backendType]);

  // Sync name with model when checkbox is checked
  useEffect(() => {
    if (syncNameWithModel && model) {
      setName(model);
    }
  }, [model, syncNameWithModel]);

  // Fetch available models when provider or API key changes
  useEffect(() => {
    const fetchModels = async () => {
      if (provider === 'custom' && !baseUrl) {
        // Don't fetch models for custom provider without base URL
        setAvailableModels([]);
        return;
      }

      try {
        const result = await listModels({
          provider,
          api_key: provider === 'custom' ? apiKey : undefined,
          base_url: provider === 'custom' ? baseUrl : undefined,
        }).unwrap();

        if (result.models && result.models.length > 0) {
          setAvailableModels(result.models);
        } else {
          // Use fallback models if API returns empty
          setAvailableModels(FALLBACK_MODELS[provider] || []);
        }
      } catch (error) {
        // Use fallback models on error
        setAvailableModels(FALLBACK_MODELS[provider] || []);
      }
    };

    fetchModels();
  }, [provider, apiKey, baseUrl, listModels]);

  // Filter models based on search
  const filteredModels = useMemo(() => {
    if (!debouncedModelSearch) return availableModels;

    const searchLower = debouncedModelSearch.toLowerCase();
    return availableModels.filter((m) => m.toLowerCase().includes(searchLower));
  }, [availableModels, debouncedModelSearch]);

  const validateForm = (): boolean => {
    const newErrors: typeof errors = {};

    // Validate name
    if (!name.trim()) {
      newErrors.name = 'Name is required';
    }

    // Validate model
    if (!model.trim()) {
      newErrors.model = 'Model is required';
    }

    // Validate base URL for custom provider
    if (provider === 'custom' && !baseUrl.trim()) {
      newErrors.base_url = 'Base URL is required for custom provider';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = () => {
    if (validateForm() && onSave) {
      if (backendType === 'openai_compatible') {
        onSave({
          backend_type: 'openai_compatible',
          name: name.trim(),
          provider,
          model: model.trim(),
          api_key: apiKey.trim() || undefined,
          base_url: baseUrl.trim() || undefined,
        });
      } else {
        onSave({
          backend_type: 'anthropic_compatible',
          name: name.trim(),
          provider,
          model: model.trim(),
          max_tokens: maxTokens,
          thinking_type: thinkingType,
          thinking_budget_tokens:
            thinkingType === 'enabled' ? thinkingBudgetTokens : undefined,
          api_key: apiKey.trim() || undefined,
          base_url: baseUrl.trim() || undefined,
        });
      }
    }
  };

  const handleFork = () => {
    if (onFork && initialValue && initialValue.name) {
      const forkedData = {
        ...initialValue,
        name: getNextForkName(initialValue.name),
      } as BackendData;
      onFork(forkedData);
    }
  };

  const handleProviderChange = (newProvider: string) => {
    setProvider(newProvider);
    // Clear model selection when provider changes
    setModel('');
    setModelSearch('');
  };

  return (
    <div className="flex flex-col h-full m-6">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b">
        <div>
          <h2 className="text-lg font-semibold">
            {readOnly
              ? 'View Backend Configuration'
              : initialValue
                ? 'Edit Backend Configuration'
                : 'New Backend Configuration'}
          </h2>
          {readOnly && initialValue ? (
            <p className="text-xs text-muted-foreground mt-1">
              Read-only view of &quot;{initialValue.name}&quot;
            </p>
          ) : initialValue ? (
            <p className="text-xs text-muted-foreground mt-1">
              Note: Editing will create a new version of this backend
              configuration
            </p>
          ) : null}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleClose}
          className="h-8 w-8 p-0"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Form Content */}
      <div className="flex-1 overflow-y-auto py-4 space-y-4">
        {/* Backend Type - show for all, selector only for new */}
        <div className="space-y-2">
          <Label htmlFor="backend-type">Backend Type</Label>
          {readOnly || initialValue ? (
            <div className="px-3 py-2 bg-muted rounded-md border text-sm">
              {backendType === 'anthropic_compatible'
                ? 'Anthropic-Compatible'
                : 'OpenAI-Compatible'}
            </div>
          ) : (
            <Select
              value={backendType}
              onValueChange={(value: BackendType) => {
                setBackendType(value);
                if (value === 'anthropic_compatible') {
                  setProvider('anthropic');
                } else {
                  setProvider('openai');
                }
              }}
            >
              <SelectTrigger id="backend-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="openai_compatible">
                  OpenAI-Compatible
                </SelectItem>
                <SelectItem value="anthropic_compatible">
                  Anthropic-Compatible
                </SelectItem>
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Provider Field */}
        <div className="space-y-2">
          <Label htmlFor="backend-provider">
            {readOnly ? 'Provider' : 'Provider *'}
          </Label>
          {readOnly ? (
            <div className="px-3 py-2 bg-muted rounded-md border text-sm">
              {(backendType === 'anthropic_compatible'
                ? ANTHROPIC_COMPATIBLE_PROVIDER_OPTIONS
                : OPENAI_COMPATIBLE_PROVIDER_OPTIONS
              ).find(
                (p: { value: string; label: string }) => p.value === provider
              )?.label || provider}
            </div>
          ) : (
            <Select value={provider} onValueChange={handleProviderChange}>
              <SelectTrigger id="backend-provider">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(backendType === 'anthropic_compatible'
                  ? ANTHROPIC_COMPATIBLE_PROVIDER_OPTIONS
                  : OPENAI_COMPATIBLE_PROVIDER_OPTIONS
                ).map((option: { value: string; label: string }) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Base URL Field */}
        <div className="space-y-2">
          <Label htmlFor="backend-base-url">Base URL</Label>
          {readOnly ? (
            <div className="px-3 py-2 bg-muted rounded-md border text-sm">
              {baseUrl || 'Default'}
            </div>
          ) : (
            <>
              <Input
                id="backend-base-url"
                name="backend-base-url"
                value={baseUrl}
                onChange={(e) => {
                  setBaseUrl(e.target.value);
                  if (errors.base_url && e.target.value.trim()) {
                    setErrors({ ...errors, base_url: undefined });
                  }
                }}
                placeholder="https://api.example.com/v1/"
                disabled={provider !== 'custom'}
                className={cn(
                  errors.base_url ? 'border-red-500' : '',
                  provider !== 'custom' ? 'bg-muted' : ''
                )}
              />
              {errors.base_url && (
                <p className="text-xs text-red-500">{errors.base_url}</p>
              )}
            </>
          )}
        </div>

        {/* API Key Field */}
        <div className="space-y-2">
          <Label htmlFor="backend-api-key">API Key</Label>
          {readOnly ? (
            <div className="px-3 py-2 bg-muted rounded-md border text-sm">
              {apiKey
                ? '••••••••'
                : provider !== 'custom'
                  ? 'Using default API key'
                  : 'Not set'}
            </div>
          ) : (
            <>
              <Input
                id="backend-api-key"
                name="backend-api-key"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  provider === 'custom'
                    ? 'Enter API key'
                    : 'Using default API key'
                }
                disabled={provider !== 'custom'}
                className={provider !== 'custom' ? 'bg-muted' : ''}
              />
              {provider !== 'custom' && (
                <p className="text-xs text-muted-foreground">
                  API key is managed by the system for{' '}
                  {
                    (backendType === 'anthropic_compatible'
                      ? ANTHROPIC_COMPATIBLE_PROVIDER_OPTIONS
                      : OPENAI_COMPATIBLE_PROVIDER_OPTIONS
                    ).find(
                      (p: { value: string; label: string }) =>
                        p.value === provider
                    )?.label
                  }
                </p>
              )}
            </>
          )}
        </div>

        {/* Model Field with Autocomplete */}
        <div className="space-y-2">
          <Label htmlFor="backend-model">
            {readOnly ? 'Model' : 'Model *'}
          </Label>
          {readOnly ? (
            <div className="px-3 py-2 bg-muted rounded-md border text-sm">
              {model || 'Not set'}
            </div>
          ) : (
            <Popover open={modelOpen} onOpenChange={setModelOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={modelOpen}
                  className={cn(
                    'w-full justify-between text-left font-normal',
                    !model && 'text-muted-foreground',
                    errors.model && 'border-red-500'
                  )}
                >
                  {model || 'Select or type a model...'}
                  <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-full p-0" align="start">
                <Command>
                  <CommandInput
                    placeholder="Search models..."
                    value={modelSearch}
                    onValueChange={(value) => {
                      setModelSearch(value);
                      setModel(value); // Allow custom model names
                      // Update name if synced with model
                      if (syncNameWithModel && value) {
                        setName(value);
                      }
                    }}
                  />
                  <CommandList>
                    {isLoadingModels ? (
                      <div className="flex items-center justify-center py-6">
                        <Loader2 className="h-4 w-4 animate-spin" />
                      </div>
                    ) : filteredModels.length === 0 ? (
                      <CommandEmpty>
                        {modelSearch ? (
                          <div className="text-sm">
                            No models found. Press Enter to use &quot;
                            {modelSearch}&quot;
                          </div>
                        ) : (
                          <div className="text-sm">No models available</div>
                        )}
                      </CommandEmpty>
                    ) : (
                      <CommandGroup>
                        {filteredModels.map((modelName) => (
                          <CommandItem
                            key={modelName}
                            value={modelName}
                            onSelect={(value) => {
                              setModel(value);
                              setModelSearch(value);
                              setModelOpen(false);
                              if (errors.model) {
                                setErrors({ ...errors, model: undefined });
                              }
                              // Update name if synced with model
                              if (syncNameWithModel) {
                                setName(value);
                              }
                            }}
                          >
                            {modelName}
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    )}
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          )}
          {!readOnly && errors.model && (
            <p className="text-xs text-red-500">{errors.model}</p>
          )}
          {!readOnly && (
            <p className="text-xs text-muted-foreground">
              Select from available models or type a custom model name
            </p>
          )}
        </div>

        {/* Anthropic-specific fields */}
        {backendType === 'anthropic_compatible' && (
          <>
            {/* Max Tokens Field */}
            <div className="space-y-2">
              <Label htmlFor="max-tokens">
                {readOnly ? 'Max Tokens' : 'Max Tokens *'}
              </Label>
              {readOnly ? (
                <div className="px-3 py-2 bg-muted rounded-md border text-sm">
                  {maxTokens}
                </div>
              ) : (
                <>
                  <Input
                    id="max-tokens"
                    type="number"
                    min={1}
                    value={maxTokens || ''}
                    onChange={(e) => {
                      const value = parseInt(e.target.value);
                      // Only update if it's a valid number, no bounds checking
                      if (!isNaN(value)) {
                        setMaxTokens(value);
                      } else if (e.target.value === '') {
                        // Allow clearing the field temporarily
                        setMaxTokens(0);
                      }
                    }}
                    onBlur={(e) => {
                      // Set to 4000 if empty or invalid on blur
                      const value = parseInt(e.target.value);
                      if (isNaN(value) || value < 1) {
                        setMaxTokens(4000);
                      }
                    }}
                    className={errors.max_tokens ? 'border-red-500' : ''}
                  />
                  {errors.max_tokens && (
                    <p className="text-xs text-red-500">{errors.max_tokens}</p>
                  )}
                  <p className="text-xs text-muted-foreground">
                    Maximum number of tokens to generate
                  </p>
                </>
              )}
            </div>

            {/* Thinking Configuration */}
            <div className="space-y-2">
              <Label htmlFor="thinking-type">Extended Thinking</Label>
              {readOnly ? (
                <div className="px-3 py-2 bg-muted rounded-md border text-sm">
                  {thinkingType || 'Not configured'}
                </div>
              ) : (
                <Select
                  value={thinkingType || 'none'}
                  onValueChange={(value) => {
                    if (value === 'none') {
                      setThinkingType(undefined);
                    } else {
                      setThinkingType(value as 'enabled' | 'disabled');
                    }
                  }}
                >
                  <SelectTrigger id="thinking-type">
                    <SelectValue placeholder="Select thinking configuration" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="disabled">Disabled</SelectItem>
                    <SelectItem value="enabled">Enabled</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* Thinking Budget Tokens */}
            {thinkingType === 'enabled' && (
              <div className="space-y-2">
                <Label htmlFor="thinking-budget-tokens">
                  {readOnly
                    ? 'Thinking Budget Tokens'
                    : 'Thinking Budget Tokens *'}
                </Label>
                {readOnly ? (
                  <div className="px-3 py-2 bg-muted rounded-md border text-sm">
                    {thinkingBudgetTokens}
                  </div>
                ) : (
                  <>
                    <Input
                      id="thinking-budget-tokens"
                      type="number"
                      min={1024}
                      max={maxTokens - 1}
                      value={thinkingBudgetTokens || ''}
                      onChange={(e) => {
                        const value = parseInt(e.target.value);
                        // Only update if it's a valid number, no bounds checking
                        if (!isNaN(value)) {
                          setThinkingBudgetTokens(value);
                        } else if (e.target.value === '') {
                          // Allow clearing the field temporarily
                          setThinkingBudgetTokens(0);
                        }
                      }}
                      onBlur={(e) => {
                        const value = parseInt(e.target.value);
                        const minValue = 1024;
                        const maxValue = maxTokens - 1;

                        // If range is invalid, default to 2000
                        if (maxTokens <= 1024) {
                          setThinkingBudgetTokens(2000);
                        } else if (isNaN(value) || value === 0) {
                          // If empty or invalid, default to 2000 but clip to range
                          setThinkingBudgetTokens(
                            Math.min(Math.max(2000, minValue), maxValue)
                          );
                        } else {
                          // Clip to valid range
                          setThinkingBudgetTokens(
                            Math.min(Math.max(value, minValue), maxValue)
                          );
                        }
                      }}
                      className={
                        errors.thinking_budget_tokens ? 'border-red-500' : ''
                      }
                    />
                    {errors.thinking_budget_tokens && (
                      <p className="text-xs text-red-500">
                        {errors.thinking_budget_tokens}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      Must be ≥1024 and less than max_tokens ({maxTokens})
                    </p>
                  </>
                )}
              </div>
            )}
          </>
        )}

        {/* Backend Name Field */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="backend-name">
              {readOnly ? 'Backend Name' : 'Backend Name *'}
            </Label>
            {!readOnly && (
              <div className="flex items-center gap-2">
                <Checkbox
                  id="sync-name"
                  checked={syncNameWithModel}
                  onCheckedChange={(checked) => {
                    setSyncNameWithModel(checked as boolean);
                    if (checked && model) {
                      setName(model);
                    }
                  }}
                />
                <Label
                  htmlFor="sync-name"
                  className="text-sm font-normal cursor-pointer"
                >
                  Set to model name
                </Label>
              </div>
            )}
          </div>
          {readOnly ? (
            <div className="px-3 py-2 bg-muted rounded-md border text-sm">
              {name || 'Not set'}
            </div>
          ) : (
            <>
              <Input
                id="backend-name"
                name="backend-name"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  if (errors.name && e.target.value.trim()) {
                    setErrors({ ...errors, name: undefined });
                  }
                }}
                placeholder=""
                disabled={syncNameWithModel}
                className={cn(
                  errors.name ? 'border-red-500' : '',
                  syncNameWithModel ? 'bg-muted' : ''
                )}
              />
              {errors.name && (
                <p className="text-xs text-red-500">{errors.name}</p>
              )}
            </>
          )}
        </div>
      </div>

      {/* Footer Actions */}
      {readOnly ? (
        <div className="flex justify-between pt-3 border-t">
          {onDelete && (
            <Button
              variant="outline"
              onClick={() => setShowDeleteDialog(true)}
              className="text-red-text hover:bg-red-muted"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Delete
            </Button>
          )}
          <div className="flex gap-2 ml-auto">
            <Button variant="outline" onClick={handleClose}>
              Close
            </Button>
            {onFork && (
              <Button onClick={handleFork}>
                <Copy className="h-4 w-4 mr-2" />
                Clone Backend Configuration
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div className="flex justify-end gap-2 pt-3 border-t">
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button onClick={handleSave}>
            {initialValue ? 'Save Changes' : 'Create Backend Configuration'}
          </Button>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      {readOnly && onDelete && (
        <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Delete Backend Configuration</DialogTitle>
              <DialogDescription className="space-y-2">
                <p>
                  Are you sure you want to delete &quot;{initialValue?.name}
                  &quot;?
                </p>
                <p className="text-sm text-muted-foreground">
                  Note: This backend configuration will be hidden from the list
                  but may still be visible in experiments that depend on it. The
                  data will not be permanently deleted to preserve experiment
                  history.
                </p>
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setShowDeleteDialog(false)}
              >
                Cancel
              </Button>
              <Button
                onClick={() => {
                  onDelete();
                  setShowDeleteDialog(false);
                }}
                className="bg-red-bg text-red-text hover:bg-red-muted"
              >
                Delete
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
