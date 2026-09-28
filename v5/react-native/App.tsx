import React from 'react';
import AppOrchestrator, {omiDotColor} from './src/app/AppOrchestrator';

export {omiDotColor};
export {resolveInitialRoute} from './src/app/routes';

export default function App({
  initialRoute,
  hostMode = false,
}: {
  initialRoute?: string;
  hostMode?: boolean;
}): React.JSX.Element {
  return <AppOrchestrator initialRoute={initialRoute} hostMode={hostMode} />;
}
