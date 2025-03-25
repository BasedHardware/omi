import React, { useEffect } from 'react';
import { useHistory } from '@docusaurus/router';

function Home() {
  const history = useHistory();

  useEffect(() => {
    history.push('/docs/developer/apps/introduction');
  }, [history]);

  return null;
}

export default Home;
