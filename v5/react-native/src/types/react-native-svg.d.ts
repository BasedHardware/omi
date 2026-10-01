import type {ComponentType} from 'react';
import type {PathProps} from 'react-native-svg';

// Top-level imports keep this file a module, so the declaration below is a
// module AUGMENTATION (merged with react-native-svg's own types) rather than
// an ambient replacement.
declare module 'react-native-svg' {
  // The runtime build names-exports every element (lib/commonjs/elements.js
  // exports.Path), but this version's bundled lib/typescript declarations
  // only export the fabric-native RNSVGPath plus the PathProps type. Declare
  // the missing component so MaterialIcon can use the documented
  // `import {Path} from 'react-native-svg'` form.
  export const Path: ComponentType<PathProps>;
}
