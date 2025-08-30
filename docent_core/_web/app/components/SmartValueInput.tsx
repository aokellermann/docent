'use client';

import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';

import { Input } from '@/components/ui/input';
import { useGetFieldValuesQuery } from '../api/collectionApi';

interface SmartValueInputProps {
  collectionId: string;
  fieldName: string;
  value: string;
  onValueChange: (value: string) => void;
  onEnter?: () => void;
  placeholder?: string;
  className?: string;
  type?: 'text' | 'number';
}

export const SmartValueInput = React.forwardRef<
  HTMLInputElement,
  SmartValueInputProps
>(
  (
    {
      collectionId,
      fieldName,
      value,
      onValueChange,
      onEnter,
      placeholder = 'Enter value...',
      className,
      type = 'text',
    },
    ref
  ) => {
    const [open, setOpen] = useState(false);
    const [inputValue, setInputValue] = useState(value);
    const [dropdownPosition, setDropdownPosition] = useState({
      top: 0,
      left: 0,
      width: 0,
    });
    const inputRef = useRef<HTMLInputElement>(null);

    const { data: fieldValuesData, isLoading } = useGetFieldValuesQuery(
      { collectionId, fieldName },
      { skip: !collectionId || !fieldName }
    );

    const values = fieldValuesData?.values || [];

    // Filter values based on input, or show all if no input
    const displayValues = inputValue
      ? values.filter((val) =>
          val.toLowerCase().includes(inputValue.toLowerCase())
        )
      : values;

    // Update input value when value prop changes
    useEffect(() => {
      setInputValue(value);
    }, [value]);

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = e.target.value;
      setInputValue(newValue);
      onValueChange(newValue);

      // Open suggestions if we have values (even when input is empty)
      if (values.length > 0) {
        updateDropdownPosition();
        setOpen(true);
      } else {
        setOpen(false);
      }
    };

    const handleSelectValue = (selectedValue: string) => {
      setInputValue(selectedValue);
      onValueChange(selectedValue);
      setOpen(false);
      // Focus back to input after selection
      setTimeout(() => inputRef.current?.focus(), 0);
    };

    const updateDropdownPosition = () => {
      // Use the forwarded ref if available, otherwise fall back to internal ref
      const currentRef = (ref as React.RefObject<HTMLInputElement>) || inputRef;
      if (currentRef?.current) {
        const rect = currentRef.current.getBoundingClientRect();
        setDropdownPosition({
          top: rect.bottom + window.scrollY,
          left: rect.left + window.scrollX,
          width: rect.width,
        });
      }
    };

    const handleInputFocus = () => {
      if (values.length > 0) {
        updateDropdownPosition();
        setOpen(true);
      }
    };

    // Handle clicking outside to close dropdown
    useEffect(() => {
      const handleClickOutside = (event: MouseEvent) => {
        // Check if the click is on the dropdown itself
        const target = event.target as Element;
        const isDropdownClick = target.closest('[data-dropdown="true"]');

        // Use the forwarded ref if available, otherwise fall back to internal ref
        const currentRef =
          (ref as React.RefObject<HTMLInputElement>) || inputRef;
        if (
          currentRef?.current &&
          !currentRef.current.contains(event.target as Node) &&
          !isDropdownClick
        ) {
          setOpen(false);
        }
      };

      if (open) {
        document.addEventListener('mousedown', handleClickOutside);
        return () =>
          document.removeEventListener('mousedown', handleClickOutside);
      }
    }, [open, ref]);

    const handleInputBlur = () => {
      // Delay closing to allow for selection
      setTimeout(() => setOpen(false), 200);
    };

    return (
      <div className="relative">
        <Input
          ref={ref || inputRef}
          value={inputValue}
          onChange={handleInputChange}
          onFocus={handleInputFocus}
          onBlur={handleInputBlur}
          placeholder={placeholder}
          type={type}
          className={cn(
            'h-7 text-xs bg-background font-mono text-muted-foreground',
            className
          )}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              onEnter?.();
            }
          }}
        />
        {open &&
          values.length > 0 &&
          typeof window !== 'undefined' &&
          createPortal(
            <div
              data-dropdown="true"
              className="fixed z-[9999] bg-background border border-border rounded-md shadow-lg max-h-48 overflow-y-auto"
              style={{
                top: `${dropdownPosition.top + 4}px`,
                left: `${dropdownPosition.left}px`,
                width: `${dropdownPosition.width}px`,
              }}
            >
              <div className="p-1">
                {displayValues.length > 0 ? (
                  displayValues.map((val) => (
                    <div
                      key={val}
                      className={cn(
                        'px-2 py-1 text-xs font-mono cursor-pointer hover:bg-secondary rounded-sm',
                        inputValue === val && 'bg-secondary'
                      )}
                      onClick={() => handleSelectValue(val)}
                    >
                      {val}
                    </div>
                  ))
                ) : (
                  <div className="px-2 py-2 text-xs text-muted-foreground text-center">
                    No matches found
                  </div>
                )}
              </div>
            </div>,
            document.body
          )}
      </div>
    );
  }
);

SmartValueInput.displayName = 'SmartValueInput';
