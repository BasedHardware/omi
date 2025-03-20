import React from 'react';
import { useInstantSearch } from 'react-instantsearch';

export function NoResultsBoundary({
  children,
  fallback,
}: {
  children: React.ReactNode;
  fallback: React.ReactNode;
}) {
  const { results } = useInstantSearch();

  // The `__isArtificial` flag makes sure to not display the No Results message
  // when no hits have been returned yet.
  if (!results.__isArtificial && results.nbHits === 0) {
    return (
      <>
        {fallback}
        <div hidden>{children}</div>
      </>
    );
  }

  return <>{children}</>;
}
