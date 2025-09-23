import { useMemo } from 'react';
import { KeyRound } from 'lucide-react';
import { Combobox } from '@/app/components/Combobox';
import {
  Tooltip,
  TooltipContent,
  TooltipPortal,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { ModelOption } from '@/app/store/rubricSlice';

function nameModel(model: ModelOption, shortenName = false) {
  if (shortenName) {
    // TODO: more general/clean way to shorten names like this
    if (model.model_name.startsWith('claude-sonnet-4-')) {
      return 'claude-sonnet-4';
    }
    return `${model.model_name}`;
  }

  if (model.reasoning_effort) {
    return `${model.provider}/${model.model_name} (${model.reasoning_effort} reasoning effort)`;
  }
  return `${model.provider}/${model.model_name}`;
}

interface ModelPickerProps {
  selectedModel: ModelOption;
  availableModels?: ModelOption[];
  onChange: (model: ModelOption) => void;
  disabled?: boolean;
  className?: string;
  borderless?: boolean;
  shortenName?: boolean;
}

export default function ModelPicker({
  selectedModel,
  availableModels,
  onChange,
  disabled = false,
  shortenName = false,
}: ModelPickerProps) {
  const options = useMemo(() => {
    return (
      availableModels?.map((model) => ({
        value: nameModel(model),
        label: nameModel(model),
        keywords: [model.provider, model.model_name]
          .concat(model.reasoning_effort ? [model.reasoning_effort] : [])
          .concat(model.uses_byok ? ['byok'] : []),
      })) ?? []
    );
  }, [availableModels]);

  const modelByValue = useMemo(() => {
    return new Map(
      availableModels?.map((model) => [nameModel(model), model]) ?? []
    );
  }, [availableModels]);

  const renderModelLabel = (
    model: ModelOption | undefined,
    shorten = false,
    tooltipSide: 'top' | 'right' | 'bottom' | 'left' | undefined = undefined
  ) => {
    if (!model) {
      return <span>Select model</span>;
    }
    return (
      <div className="flex flex-row items-center gap-1 w-full">
        <span className="flex-1 truncate">{nameModel(model, shorten)}</span>
        {model.uses_byok && (
          <Tooltip>
            <TooltipTrigger asChild>
              <KeyRound className="h-3 w-3 flex-shrink-0" />
            </TooltipTrigger>
            <TooltipPortal>
              <TooltipContent side={tooltipSide}>
                <p>This model uses your own API key</p>
              </TooltipContent>
            </TooltipPortal>
          </Tooltip>
        )}
      </div>
    );
  };

  return (
    <TooltipProvider>
      <Combobox
        value={nameModel(selectedModel)}
        onChange={(value) => {
          const selected = modelByValue.get(value);
          if (!selected) return;
          onChange(selected);
        }}
        options={options}
        placeholder="Select model"
        triggerProps={{ disabled }}
        triggerClassName="max-w-24"
        renderValue={() => renderModelLabel(selectedModel, shortenName, 'top')}
        renderOptionLabel={(option) => {
          const model = modelByValue.get(option.value);
          return model ? renderModelLabel(model) : option.label;
        }}
      />
    </TooltipProvider>
  );
}
