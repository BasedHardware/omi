import find from 'find';
import Jasmine from 'jasmine';
import logger from 'jet-logger';
import { argv } from 'process';


/******************************************************************************
                              Run
******************************************************************************/

// Init Jasmine
const jasmine = new Jasmine();
jasmine.exitOnCompletion = false;

// Set location of test files
jasmine.loadConfig({
  random: true,
  spec_dir: 'spec',
  spec_files: [
    './tests/**/*.spec.ts',
  ],
  stopSpecOnExpectationFailure: false,
});

// Run all or a single unit-test
let execResp: Promise<jasmine.JasmineDoneInfo> | undefined;
if (!!argv[2]) {
  const testFile = argv[2];
  find.file(testFile + '.spec.ts', './spec', (files: string[]) => {
    if (files.length === 1) {
      jasmine.execute([files[0]]);
    } else {
      logger.err('Test file not found!');
    }
  });
} else {
  execResp = jasmine.execute();
}

// Wait for tests to finish
(async () => {
  if (!!execResp) {
    const info = await execResp;
    if (info.overallStatus === 'passed') {
      logger.info('All tests have passed :)');
    } else {
      logger.err('At least one test has failed :(');
    }
  }
})();
