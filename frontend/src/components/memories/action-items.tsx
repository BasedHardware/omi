import { ActionItems as ActionItemsType } from "@/src/types/memory.types";

interface ActionsItemsProps {
  items: ActionItemsType[];
}

export default function ActionItems({ items }: ActionsItemsProps){
  return(
    <div>
      <h3>Action Items</h3>
      <ul>
        {items.map((item, index) => (
          <li key={index}>
            {item.completed ? "✅" : "❌"} {item.description}
          </li>
        ))}
      </ul>
    </div>
  )
}