'use client';

import React from 'react';
import { RefinementStatus } from '@/app/store/refinementSlice';

type Props = {
  status: RefinementStatus;
};

const steps: Array<{ key: RefinementStatus; label: string }> = [
  { key: 'reading_data', label: 'Reading data' },
  { key: 'initial_feedback', label: 'Gathering feedback' },
  { key: 'asking_questions', label: 'Asking clarifying questions' },
  { key: 'done', label: 'Rubric finalized' },
];

const statusIndex: Record<RefinementStatus, number> = {
  reading_data: 0,
  initial_feedback: 1,
  asking_questions: 2,
  done: 3,
};

export default function RefinementTimeline({ status }: Props) {
  const currentIndex = statusIndex[status] ?? 0;

  return (
    <div className="w-full">
      <div className="flex items-center">
        {steps.map((step, idx) => {
          const isCompleted = idx < currentIndex;
          const isCurrent = idx === currentIndex;

          const circleClasses = isCurrent
            ? 'bg-secondary border-primary/20 text-primary'
            : 'bg-background border-border text-muted-foreground';

          const labelClasses = isCurrent
            ? 'text-primary font-semibold underline'
            : isCompleted
              ? 'text-muted-foreground opacity-80'
              : 'text-muted-foreground opacity-60';

          const connectorClasses = isCompleted
            ? 'bg-border opacity-100'
            : 'bg-border opacity-40';

          return (
            <React.Fragment key={step.key}>
              <div className="flex items-center min-w-0">
                <div
                  className={
                    'w-6 h-6 rounded-full border flex items-center justify-center text-xs font-medium transition-colors ' +
                    circleClasses
                  }
                >
                  {isCompleted ? '✓' : idx + 1}
                </div>
                <div className={`ml-2 text-xs ${labelClasses}`}>
                  {step.label}
                </div>
              </div>
              {idx < steps.length - 1 && (
                <div className="flex-1 mx-3">
                  <div className={`h-0.5 w-full ${connectorClasses}`} />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}
