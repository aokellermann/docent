'use client';

/**
 * PortalTooltip - A tooltip component that renders outside the normal React tree
 *
 * This component uses React Portal to render tooltips directly to document.body,
 * allowing them to escape the overflow constraints of their parent containers.
 *
 * Why we need this:
 * - Nivo chart tooltips are normally rendered within the chart's SVG container
 * - The ChartsArea component has overflow:hidden/auto styling for scrolling
 * - This causes tooltips to be clipped when they extend beyond the chart boundaries
 * - By using createPortal, tooltips can extend beyond any container boundaries
 * - Provides consistent tooltip visibility regardless of chart container size
 */

import { ReactNode, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { BasicTooltip } from '@nivo/tooltip';

interface PortalTooltipProps {
  id: ReactNode;
  value?: string | number;
  color?: string;
  position?: { x: number; y: number };
  anchor?: 'top' | 'right' | 'bottom' | 'left' | 'center';
  enableChip?: boolean;
}

const TOOLTIP_OFFSET = 14;

export function PortalTooltip({
  id,
  value,
  color,
  position = { x: 0, y: 0 },
  anchor = 'top',
  enableChip = true,
}: PortalTooltipProps) {
  const [mounted, setMounted] = useState(false);
  const [tooltipElement, setTooltipElement] = useState<HTMLDivElement | null>(
    null
  );

  // Ensure component only renders on client side
  useEffect(() => {
    setMounted(true);
  }, []);

  // Calculate absolute positioning based on chart position and anchor
  const calculatePosition = () => {
    if (!tooltipElement) return { x: position.x, y: position.y };

    const rect = tooltipElement.getBoundingClientRect();
    let x = position.x;
    let y = position.y;

    // Adjust position based on anchor point
    switch (anchor) {
      case 'top':
        x -= rect.width / 2;
        y -= rect.height + TOOLTIP_OFFSET;
        break;
      case 'bottom':
        x -= rect.width / 2;
        y += TOOLTIP_OFFSET;
        break;
      case 'left':
        x -= rect.width + TOOLTIP_OFFSET;
        y -= rect.height / 2;
        break;
      case 'right':
        x += TOOLTIP_OFFSET;
        y -= rect.height / 2;
        break;
      case 'center':
        x -= rect.width / 2;
        y -= rect.height / 2;
        break;
    }

    // Prevent tooltip from going off-screen
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    if (x < 0) x = TOOLTIP_OFFSET;
    if (x + rect.width > viewportWidth)
      x = viewportWidth - rect.width - TOOLTIP_OFFSET;
    if (y < 0) y = TOOLTIP_OFFSET;
    if (y + rect.height > viewportHeight)
      y = viewportHeight - rect.height - TOOLTIP_OFFSET;

    return { x, y };
  };

  if (!mounted) return null;

  const { x, y } = calculatePosition();

  const tooltipContent = (
    <div
      ref={setTooltipElement}
      style={{
        position: 'fixed',
        left: x,
        top: y,
        pointerEvents: 'none',
        zIndex: 9999,
      }}
    >
      <BasicTooltip
        id={id}
        value={value}
        color={color}
        enableChip={enableChip}
      />
    </div>
  );

  return createPortal(tooltipContent, document.body);
}
