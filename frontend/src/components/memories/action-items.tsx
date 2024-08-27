import { ActionItems as ActionItemsType } from "@/src/types/memory.types";

interface ActionsItemsProps {
  items: ActionItemsType[];
}

export default function ActionItems({ items }: ActionsItemsProps){
  return(
    <div>
      <h3 className="text-2xl font-semibold">Action Items</h3>
      <ul className="mt-3">
        {items.map((item, index) => (
          <li key={index} className="my-2">
            <p>
              {item.completed ? "✅" : "❌"} {item.description}
            </p>
          </li>
        ))}
      </ul>
    </div>
  )
}