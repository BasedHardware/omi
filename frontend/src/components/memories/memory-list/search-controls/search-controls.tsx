'use client';

import { liteClient as algoliasearch } from 'algoliasearch/lite';
import SearchBar from './search-bar';
import { InstantSearch, Configure} from 'react-instantsearch';
import { Fragment } from 'react';
import envConfig from '@/src/constants/envConfig';

console.log(envConfig);
const searchClient = algoliasearch(envConfig.ALGOLIA_APP_ID, envConfig.ALGOLIA_SEARCH_API_KEY);

interface SearchControlsProps {
  children: React.ReactNode;
}

export default function SearchControls({ children }: SearchControlsProps) {

  return (
    <Fragment>
      <h1 className="text-center mt-10 text-3xl font-bold text-white">Memories</h1>
      <InstantSearch searchClient={searchClient} indexName={envConfig.ALGOLIA_INDEX_NAME} routing={true}>
        <Configure hitsPerPage={15} />
        <SearchBar />
        {children}       
      </InstantSearch>
    </Fragment>
  );
}