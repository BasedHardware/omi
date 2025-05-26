'use client';

import { Fragment, useState } from 'react';
import Tabs from '../tabs';
import Summary from './sumary';
import Transcription from '../transcript/transcription';
import { Memory } from '@/src/types/memory.types';

interface MemoryWithTabsProps {
  memory: Memory;
}

export default function MemoryWithTabs({ memory }: MemoryWithTabsProps) {
  const [currentTab, setCurrentTab] = useState('sum');
  return (
    <Fragment>
      <Tabs currentTab={currentTab} setCurrentTab={setCurrentTab} />
      <div className="">
        {currentTab === 'sum' ? (
          <Summary memory={memory} />
        ) : (
          <Transcription
            transcript={memory.transcript_segments}
            externalData={memory.external_data}
          />
        )}
      </div>
    </Fragment>
  );
}
