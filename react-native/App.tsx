import React from 'react';
import AppOrchestrator, {omiDotColor} from './src/app/AppOrchestrator';

export {omiDotColor};
export {resolveInitialRoute} from './src/app/routes';

export default function App({
  initialRoute,
}: {
  initialRoute?: string;
}): React.JSX.Element {
  return <AppOrchestrator initialRoute={initialRoute} />;
}
