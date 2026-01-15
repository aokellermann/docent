'use client';

import {
  type ComponentPropsWithoutRef,
  type CSSProperties,
  type ReactNode,
  type RefObject,
  useCallback,
  useMemo,
  useState,
} from 'react';
import { Button } from '@/components/ui/button';
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
import { Check, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';

export type ComboboxOption = {
  value: string;
  label: ReactNode;
  keywords?: string[];
  disabled?: boolean;
};

type ButtonProps = ComponentPropsWithoutRef<typeof Button>;
type PopoverContentProps = ComponentPropsWithoutRef<typeof PopoverContent>;

export type ComboboxActionItem = {
  key: string;
  label: ReactNode;
  onSelect: () => void;
  keywords?: string[];
  className?: string;
  icon?: ReactNode;
  disabled?: boolean;
  closeOnSelect?: boolean;
};

type BaseComboboxProps = {
  options: ComboboxOption[];
  placeholder?: ReactNode;
  searchPlaceholder?: string;
  emptyMessage?: ReactNode;
  triggerProps?: Omit<ButtonProps, 'children'>;
  triggerClassName?: string;
  valueClassName?: string;
  popoverClassName?: string;
  popoverStyle?: CSSProperties;
  popoverAlign?: PopoverContentProps['align'];
  popoverSide?: PopoverContentProps['side'];
  popoverSideOffset?: PopoverContentProps['sideOffset'];
  popoverAlignOffset?: PopoverContentProps['alignOffset'];
  commandInputClassName?: string;
  commandInputRef?: RefObject<HTMLInputElement>;
  commandListClassName?: string;
  optionClassName?: string;
  actionItems?: ComboboxActionItem[];
  closeOnSelect?: boolean;
  renderOptionLabel?: (option: ComboboxOption) => ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  headerContent?: ReactNode;
};

type SingleComboboxProps = BaseComboboxProps & {
  value: string | null;
  onChange: (value: string) => void;
  renderValue?: (selected: ComboboxOption | null) => ReactNode;
};

type MultiComboboxProps = BaseComboboxProps & {
  values: string[];
  onChange: (values: string[]) => void;
  renderValue?: (selected: ComboboxOption[]) => ReactNode;
};

type ComboboxBaseProps = BaseComboboxProps & {
  displayValue: ReactNode;
  isOptionSelected: (option: ComboboxOption) => boolean;
  onSelectOption: (value: string) => void;
  closeOnSelect: boolean;
};

// Internal renderer shared by both single and multi-select variants.
const ComboboxBase = ({
  options,
  placeholder = 'Select option',
  searchPlaceholder = 'Search...',
  emptyMessage = 'No results found.',
  triggerProps,
  triggerClassName,
  valueClassName,
  popoverClassName,
  popoverStyle,
  popoverAlign,
  popoverSide,
  popoverSideOffset,
  popoverAlignOffset,
  commandInputClassName,
  commandInputRef,
  commandListClassName,
  optionClassName,
  actionItems,
  renderOptionLabel,
  open,
  onOpenChange,
  headerContent,
  displayValue,
  isOptionSelected,
  onSelectOption,
  closeOnSelect,
}: ComboboxBaseProps) => {
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = open !== undefined;
  const isOpen = isControlled ? Boolean(open) : internalOpen;

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!isControlled) {
        setInternalOpen(nextOpen);
      }
      onOpenChange?.(nextOpen);
    },
    [isControlled, onOpenChange]
  );

  const handleSelect = useCallback(
    (nextValue: string) => {
      onSelectOption(nextValue);
      if (closeOnSelect) {
        handleOpenChange(false);
      }
    },
    [closeOnSelect, handleOpenChange, onSelectOption]
  );

  const {
    className: triggerPropsClassName,
    variant = 'outline',
    ...restTriggerProps
  } = triggerProps ?? {};

  return (
    <Popover open={isOpen} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button
          variant={variant}
          size="sm"
          role="combobox"
          aria-expanded={isOpen}
          {...restTriggerProps}
          className={cn(
            'w-full justify-between',
            triggerPropsClassName,
            triggerClassName
          )}
        >
          <span className={cn('flex-1 truncate text-left', valueClassName)}>
            {displayValue ?? placeholder}
          </span>
          <ChevronsUpDown
            className="ml-2 h-3 w-3 shrink-0 opacity-50"
            aria-hidden="true"
          />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className={cn('p-0', popoverClassName)}
        style={popoverStyle}
        align={popoverAlign}
        side={popoverSide}
        sideOffset={popoverSideOffset}
        alignOffset={popoverAlignOffset}
      >
        {headerContent}
        <Command>
          <CommandInput
            placeholder={searchPlaceholder}
            className={cn('h-8 text-xs', commandInputClassName)}
            ref={commandInputRef}
          />
          <CommandList className={cn('custom-scrollbar', commandListClassName)}>
            <CommandEmpty>
              <span className="text-xs">{emptyMessage}</span>
            </CommandEmpty>
            {actionItems?.length ? (
              <CommandGroup>
                {actionItems.map((action) => {
                  const shouldClose = action.closeOnSelect ?? closeOnSelect;
                  return (
                    <CommandItem
                      key={action.key}
                      value={action.key}
                      keywords={action.keywords}
                      disabled={action.disabled}
                      onSelect={() => {
                        action.onSelect();
                        if (shouldClose) {
                          handleOpenChange(false);
                        }
                      }}
                      className={cn(
                        'flex items-center text-xs',
                        action.className
                      )}
                    >
                      {action.icon ? (
                        <span className="mr-2 flex h-4 w-4 items-center justify-center text-muted-foreground">
                          {action.icon}
                        </span>
                      ) : null}
                      {action.label}
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            ) : null}
            <CommandGroup>
              {options.map((option) => {
                const isSelected = isOptionSelected(option);
                return (
                  <CommandItem
                    key={option.value}
                    value={option.value}
                    keywords={option.keywords}
                    disabled={option.disabled}
                    onSelect={() => handleSelect(option.value)}
                    className={cn('flex items-center text-xs', optionClassName)}
                  >
                    {renderOptionLabel
                      ? renderOptionLabel(option)
                      : option.label}
                    <Check
                      aria-hidden="true"
                      className={cn(
                        'ml-auto h-4 w-4',
                        isSelected ? 'opacity-100' : 'opacity-0'
                      )}
                    />
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
};

export const SingleCombobox = ({
  options,
  value,
  onChange,
  renderValue,
  placeholder = 'Select option',
  closeOnSelect,
  ...rest
}: SingleComboboxProps) => {
  const selectedOption = useMemo(() => {
    if (value === null || value === undefined) {
      return null;
    }
    return options.find((option) => option.value === value) ?? null;
  }, [options, value]);

  const displayValue = useMemo(() => {
    if (renderValue) {
      return renderValue(selectedOption);
    }
    return selectedOption?.label ?? placeholder;
  }, [placeholder, renderValue, selectedOption]);

  const resolvedCloseOnSelect = closeOnSelect ?? true;

  const handleSelect = useCallback(
    (nextValue: string) => {
      onChange(nextValue);
    },
    [onChange]
  );

  return (
    <ComboboxBase
      {...rest}
      options={options}
      placeholder={placeholder}
      displayValue={displayValue}
      isOptionSelected={(option) => option.value === value}
      onSelectOption={handleSelect}
      closeOnSelect={resolvedCloseOnSelect}
    />
  );
};

export const MultiCombobox = ({
  options,
  values,
  onChange,
  renderValue,
  placeholder = 'Select option',
  closeOnSelect,
  ...rest
}: MultiComboboxProps) => {
  const selectedOptions = useMemo(() => {
    const selectedSet = new Set(values);
    return options.filter((option) => selectedSet.has(option.value));
  }, [options, values]);

  const displayValue = useMemo(() => {
    if (renderValue) {
      return renderValue(selectedOptions);
    }
    if (!selectedOptions.length) {
      return placeholder;
    }
    if (selectedOptions.length === 1) {
      return selectedOptions[0].label;
    }
    return `${selectedOptions.length} selected`;
  }, [placeholder, renderValue, selectedOptions]);

  const resolvedCloseOnSelect = closeOnSelect ?? false;

  const handleSelect = useCallback(
    (nextValue: string) => {
      const exists = values.includes(nextValue);
      const nextValues = exists
        ? values.filter((value) => value !== nextValue)
        : [...values, nextValue];
      onChange(nextValues);
    },
    [onChange, values]
  );

  return (
    <ComboboxBase
      {...rest}
      options={options}
      placeholder={placeholder}
      displayValue={displayValue}
      isOptionSelected={(option) => values.includes(option.value)}
      onSelectOption={handleSelect}
      closeOnSelect={resolvedCloseOnSelect}
    />
  );
};

export { SingleCombobox as Combobox };
