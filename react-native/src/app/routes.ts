export type Route =
  | 'Home'
  | 'Conversations'
  | 'Memories'
  | 'Tasks'
  | 'Connectors'
  | 'Settings';

const routes: ReadonlySet<string> = new Set([
  'Home',
  'Conversations',
  'Memories',
  'Tasks',
  'Connectors',
  'Settings',
]);

export function resolveInitialRoute(initialRoute?: string): Route {
  return initialRoute !== undefined && routes.has(initialRoute)
    ? (initialRoute as Route)
    : 'Home';
}
