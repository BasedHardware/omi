'use client';
import { FC, ReactNode, useEffect } from 'react';
import Gleap from 'gleap';

export const GleapInit: FC<{ children?: ReactNode }> = ({ children }) => {
  useEffect(() => {
    Gleap.initialize('TkYt8vtmccX6UBfSdo2I45lYYSEEC8Fn');
  });
  return <>{children}</>;
};