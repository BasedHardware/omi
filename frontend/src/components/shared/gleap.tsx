'use client';
import { FC, ReactNode, useEffect } from 'react';
import Gleap from 'gleap';
import envConfig from '@/src/constants/envConfig';

export const GleapInit: FC<{ children?: ReactNode }> = ({ children }) => {
  useEffect(() => {
    Gleap.initialize(envConfig.GLEAP_API_KEY ?? '');
  }, []);
  return <>{children}</>;
};
