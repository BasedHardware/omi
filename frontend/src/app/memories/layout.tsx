import AppHeader from "@/src/components/shared/app-header";

export default function MemoriesLayout({ children }){
  return (
    <div>
      <AppHeader />
      {children}
    </div>
  )
}