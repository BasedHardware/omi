import Link from "next/link";

export default function Tabs({ currentTab }: { currentTab: string }){
  return (
    <div className="flex text-lg border-y border-solid border-zinc-800 mt-10">
      <Link href="?tab=sum" className={`${currentTab === 'sum' ? "bg-zinc-800" : ""} py-3 w-full text-center`}>
        Summary
      </Link>
      <Link href="?tab=trs" className={`${currentTab === 'trs' ? "bg-zinc-800" : ""} py-3 w-full text-center`}>
        Transcript
      </Link>
    </div>
  )
}