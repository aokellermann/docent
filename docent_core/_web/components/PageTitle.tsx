'use client';

import { useEffect } from 'react';

interface PageTitleProps {
  title: string;
}

export function PageTitle({ title }: PageTitleProps) {
  useEffect(() => {
    document.title = `Docent | ${title}`;
  }, [title]);

  return null;
}
