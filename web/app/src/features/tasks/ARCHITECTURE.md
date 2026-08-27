# tasks

Destination `/tasks`. `useHomeTasks` is also consumed by the home hub.

- `api.ts` — action-item CRUD
- `model.ts` — due labels and due-window grouping
- `useActionItems.ts` — `createActionItemsStore` (optimistic list)
- `useHomeTasks.ts` — `useAsyncResource` for the hub's short open-task list
- `taskExport.ts` — copy/download
- `ui/` — hub, cards, calendar, bulk bar
