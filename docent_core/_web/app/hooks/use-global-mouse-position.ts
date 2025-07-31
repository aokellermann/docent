'use client';

import { useState, useEffect } from 'react';

// Global mouse position tracker
let globalMousePosition = { x: 0, y: 0 };
let listeners: Array<(position: { x: number; y: number }) => void> = [];
let isInitialized = false;
let handleMouseMove: ((event: MouseEvent) => void) | null = null;

// Initialize global mouse tracking only once
const initializeGlobalMouseTracking = () => {
  if (isInitialized) return;

  handleMouseMove = (event: MouseEvent) => {
    globalMousePosition = { x: event.clientX, y: event.clientY };
    listeners.forEach((listener) => listener(globalMousePosition));
  };

  document.addEventListener('mousemove', handleMouseMove, { passive: true });
  isInitialized = true;
};

// Cleanup global mouse tracking when no listeners remain
const cleanupGlobalMouseTracking = () => {
  if (!isInitialized || listeners.length > 0) return;

  if (handleMouseMove) {
    document.removeEventListener('mousemove', handleMouseMove);
    handleMouseMove = null;
  }
  isInitialized = false;
};

/**
 * Hook that provides instant access to current mouse position.
 * Uses a global mouse tracker to eliminate setup delays that cause tooltip flashing.
 */
export function useGlobalMousePosition() {
  const [position, setPosition] = useState(globalMousePosition);

  useEffect(() => {
    // Initialize global tracking if not already done
    initializeGlobalMouseTracking();

    // Add this component's listener
    listeners.push(setPosition);

    // Set initial position in case mouse hasn't moved yet
    setPosition(globalMousePosition);

    // Cleanup listener on unmount
    return () => {
      listeners = listeners.filter((listener) => listener !== setPosition);
      cleanupGlobalMouseTracking();
    };
  }, []);

  return position;
}
