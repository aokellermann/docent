'use client';

import { PortalTooltip } from './PortalTooltip';
import { useGlobalMousePosition } from '../hooks/use-global-mouse-position';

interface BarTooltipProps {
  color: string;
  label: string;
  value: number;
  formattedValue?: string;
  [key: string]: any; // Allow additional computed datum properties
}

interface LinePointData {
  xFormatted?: string;
  yFormatted?: string;
  [key: string]: any;
}

interface LineTooltipPoint {
  seriesId: string;
  seriesColor: string;
  data?: LinePointData;
  [key: string]: any;
}

interface LineTooltipProps {
  point: LineTooltipPoint;
  [key: string]: any;
}

// Custom tooltip for Bar charts
export function CustomBarTooltip(props: BarTooltipProps | null) {
  const mousePosition = useGlobalMousePosition();

  if (!props) return null;

  const { color, label, value, formattedValue } = props;

  return (
    <PortalTooltip
      id={label}
      value={formattedValue || value}
      color={color}
      position={mousePosition}
      anchor="top"
    />
  );
}

// Custom tooltip for Line charts
export function CustomLineTooltip(props: LineTooltipProps | null) {
  const mousePosition = useGlobalMousePosition();

  if (!props) return null;

  const { point } = props;
  if (!point) return null;

  return (
    <PortalTooltip
      id={`${point.seriesId}: ${point.data?.xFormatted}`}
      value={point.data?.yFormatted}
      color={point.seriesColor}
      position={mousePosition}
      anchor="top"
    />
  );
}
