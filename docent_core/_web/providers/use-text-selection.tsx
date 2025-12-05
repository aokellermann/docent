'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  CitationTarget,
  TranscriptBlockContentItem,
} from '@/app/types/citationTypes';
import { useAppDispatch, useAppSelector } from '@/app/store/hooks';
import {
  setTextSelections,
  selectTextSelections,
} from '@/app/store/transcriptSlice';
import { reverseTransformPrettyPrintIndices } from '@/lib/citationMatch';

export type TextSelectionItem = {
  text: string;
  citation?: CitationTarget;
};

type TextSelectionContextValue = {
  focusChatInput: () => void;
  menuElement?: React.ReactNode;
};

const defaultValue: TextSelectionContextValue = {
  focusChatInput: () => {},
  menuElement: undefined,
};

const TextSelectionContext =
  createContext<TextSelectionContextValue>(defaultValue);

type MenuState = {
  citation: CitationTarget;
  text: string;
  position: { top: number; left: number };
};

type UseTextSelectionProps = {
  containerRef?: React.RefObject<HTMLElement | null>;
  triggers?: {
    mouseup?: boolean;
    hotkey?: boolean;
  };
  renderMenu?: (ctx: {
    citation: CitationTarget;
    text: string;
    position: { top: number; left: number };
    dismiss: () => void;
  }) => React.ReactNode;
};

/**
 * Gets the nearest citation context element for a given node.
 */
function getContextElement(
  node: Node,
  boundary: HTMLElement
): HTMLElement | null {
  const element =
    node.nodeType === Node.TEXT_NODE ? node.parentElement : (node as Element);
  const contextElement = element?.closest(
    '[data-citation-context]'
  ) as HTMLElement | null;
  if (!contextElement || !boundary.contains(contextElement)) {
    return null;
  }
  return contextElement;
}

/**
 * Computes a citation from a text selection range by finding the nearest
 * ancestor element with a data-citation-context attribute.
 * Returns undefined if selection spans multiple content items.
 * Handles reverse-mapping indices when content is pretty-printed.
 */
function getCitationFromRange(
  range: Range,
  selectedText: string,
  boundary: HTMLElement | null
): CitationTarget | undefined {
  if (!boundary || !boundary.contains(range.commonAncestorContainer as Node)) {
    return undefined;
  }

  // Find context elements for start and end of selection
  const startContext = getContextElement(range.startContainer, boundary);
  const endContext = getContextElement(range.endContainer, boundary);

  // If selection spans multiple context elements (or either is missing), don't show menu
  if (!startContext || !endContext || startContext !== endContext) {
    return undefined;
  }

  const contextElement = startContext;

  try {
    const contextData = contextElement.dataset.citationContext;
    if (!contextData) return undefined;

    const context: TranscriptBlockContentItem = JSON.parse(contextData);

    // Calculate the start position of the selected text within the rendered content
    const preRange = document.createRange();
    preRange.setStart(contextElement, 0);
    preRange.setEnd(range.startContainer, range.startOffset);
    const textBeforeSelection = preRange.toString();
    let target_start_idx = textBeforeSelection.length;
    let target_end_idx = target_start_idx + selectedText.length;

    // Check for original text (indicates content is transformed, e.g. pretty-printed JSON)
    // If present, reverse-map indices to get positions in the original text
    const originalText = contextElement.dataset.originalText;
    if (originalText) {
      const renderedText = contextElement.textContent || '';
      const reversed = reverseTransformPrettyPrintIndices(
        target_start_idx,
        target_end_idx,
        originalText,
        renderedText
      );
      target_start_idx = reversed.startIdx;
      target_end_idx = reversed.endIdx;
    }

    return {
      item: context,
      text_range: {
        target_start_idx,
        target_end_idx,
        start_pattern: null,
        end_pattern: null,
      },
    };
  } catch (e) {
    console.error('Failed to parse citation context', e);
    return undefined;
  }
}

type UseTextSelectionResult = TextSelectionContextValue & {
  selections: TextSelectionItem[];
  removeSelection: (index: number) => void;
  clearSelections: () => void;
};

export function useTextSelection({
  containerRef,
  triggers = { hotkey: true },
  renderMenu,
}: UseTextSelectionProps): UseTextSelectionResult {
  const textSelectionContext = useContext(TextSelectionContext);
  const dispatch = useAppDispatch();
  const selections = useAppSelector(selectTextSelections);
  const [menuState, setMenuState] = useState<MenuState | null>(null);
  const menuStateRef = useRef<MenuState | null>(null);

  // Keep ref in sync with state
  useEffect(() => {
    menuStateRef.current = menuState;
  }, [menuState]);

  const removeSelection = useCallback(
    (index: number) => {
      const newSelections = [...selections];
      newSelections.splice(index, 1);
      dispatch(setTextSelections(newSelections));
    },
    [selections, dispatch]
  );

  const clearSelections = useCallback(() => {
    dispatch(setTextSelections([]));
  }, [dispatch]);

  // Mouseup handler for citation computation and menu display
  useEffect(() => {
    if (!containerRef || !triggers?.mouseup) return;

    const handleMouseUp = () => {
      const boundary = containerRef.current;
      if (!boundary) return;

      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.rangeCount) {
        setMenuState(null);
        return;
      }

      const range = selection.getRangeAt(0);
      const selectedText = selection.toString().trim();
      if (!selectedText || selectedText.length < 2) {
        setMenuState(null);
        return;
      }

      // Get citation from the text selection range
      const citation = getCitationFromRange(range, selectedText, boundary);
      if (!citation) {
        setMenuState(null);
        return;
      }

      // Get button position in content coordinates (including scroll offset)
      // so the menu scrolls with the text
      const rect = range.getBoundingClientRect();
      const containerRect = boundary.getBoundingClientRect();
      const buttonTop =
        rect.bottom - containerRect.top + boundary.scrollTop + 4;
      const buttonLeft = rect.left - containerRect.left + boundary.scrollLeft;

      setMenuState({
        citation,
        text: selectedText,
        position: { top: buttonTop, left: buttonLeft },
      });
    };

    // Handle click outside to dismiss menu
    const handleClickOutside = (e: MouseEvent) => {
      // Small delay to ensure event propagation completes
      setTimeout(() => {
        // Only dismiss if there's a menu and the click is outside the menu
        // Also check that there's no active selection (user might be selecting text)
        const selection = window.getSelection();
        const hasSelection =
          selection && !selection.isCollapsed && selection.rangeCount > 0;

        if (
          menuStateRef.current &&
          !hasSelection &&
          !(e.target as HTMLElement).closest('[data-text-selection-menu]')
        ) {
          setMenuState(null);
          window.getSelection()?.removeAllRanges();
        }
      }, 20);
    };

    // Attach to document since selection can end outside but we want to capture it if it started inside?
    // Actually, the original code attached to document. Ideally we scope to container if possible,
    // but selection events bubble.
    // We'll stick to document listeners but check boundary in handler.
    document.addEventListener('mouseup', handleMouseUp);
    document.addEventListener('mouseup', handleClickOutside);
    return () => {
      document.removeEventListener('mouseup', handleMouseUp);
      document.removeEventListener('mouseup', handleClickOutside);
    };
  }, [containerRef, triggers?.mouseup]);

  // Hotkey handler (Ctrl/Cmd+I)
  useEffect(() => {
    if (!containerRef || !triggers?.hotkey) return;
    const handler = (e: KeyboardEvent) => {
      // Ctrl+I shortcut
      const isModifier = e.metaKey || e.ctrlKey;
      if (isModifier && (e.key === 'i' || e.key === 'I')) {
        const container = containerRef.current;
        if (!container) return;
        const sel = window.getSelection();
        if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return;
        const range = sel.getRangeAt(0);
        if (!container.contains(range.commonAncestorContainer as Node)) return;
        const selected = sel.toString().trim();
        if (!selected) return;
        e.preventDefault();

        // Compute citation
        const citation = getCitationFromRange(range, selected, container);

        const item: TextSelectionItem = citation
          ? { citation, text: selected }
          : { text: selected };

        // Add to Redux state
        const text = (item.text || '').trim();
        if (text) {
          // Avoid immediate duplicates
          const shouldAdd =
            selections.length === 0 ||
            selections[selections.length - 1]?.text !== text;
          if (shouldAdd) {
            dispatch(setTextSelections([...selections, { ...item, text }]));
          }
        }

        textSelectionContext.focusChatInput();
        try {
          sel.removeAllRanges();
        } catch {
          console.error('Failed to remove ranges from text selection');
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [
    containerRef,
    triggers?.hotkey,
    textSelectionContext,
    dispatch,
    selections,
  ]);

  // Render menu element
  const menuElement = useMemo(() => {
    if (!menuState || !renderMenu || !containerRef?.current) {
      return undefined;
    }

    const dismiss = () => {
      setMenuState(null);
      window.getSelection()?.removeAllRanges();
    };

    // Position is already in content coordinates (scroll offset included at capture time)
    // so it naturally scrolls with the content
    return (
      <div
        data-text-selection-menu
        className="absolute z-50"
        style={{
          top: `${menuState.position.top}px`,
          left: `${menuState.position.left}px`,
        }}
      >
        {renderMenu({
          citation: menuState.citation,
          text: menuState.text,
          position: menuState.position,
          dismiss,
        })}
      </div>
    );
  }, [menuState, renderMenu, containerRef]);

  // Do not throw if not inside provider; return context (possibly default no-op)
  const contextValue = textSelectionContext ?? defaultValue;
  return {
    ...contextValue,
    menuElement,
    selections,
    removeSelection,
    clearSelections,
  };
}

export function TextSelectionProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const focusChatInput = useCallback(() => {
    try {
      window.dispatchEvent(new Event('focus-chat-input' as any));
    } catch {
      console.error('Failed to focus chat input from text selection provider');
    }
  }, []);

  const value = useMemo(
    () => ({
      focusChatInput,
    }),
    [focusChatInput]
  );

  return (
    <TextSelectionContext.Provider value={value}>
      {children}
    </TextSelectionContext.Provider>
  );
}
