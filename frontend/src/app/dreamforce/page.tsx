import { Trend } from "@/src/types/trends/trends.types";

const trendMock: Trend[] = [
  {
    create_at: new Date(),
    category: "Dreamforce",
    id: "1",
    topics: [
      {
        id: "1",
        topic: "Salesforce",
        memories_count: 100
      },
      {
        id: "2",
        topic: "Trailhead",
        memories_count: 50
      },
      {
        id: "3",
        topic: "Dreamforce",
        memories_count: 10
      },
    ]
  },
    {
    create_at: new Date(),
    category: "Investment",
    id: "2",
    topics: [
      {
        id: "1",
        topic: "Investors",
        memories_count: 4
      },
      {
        id: "2",
        topic: "Trailhead",
        memories_count: 32
      }
    ]
  }
]

export default function DreamforcePage(){
  return (
    <div className="flex w-full px-4 bg-[url(/noise-texture.svg)] min-h-screen bg-[#09090b]">
      <div className="mx-auto w-full max-w-screen-xl my-44">
        <h1 className="text-white text-center font-semibold text-4xl md:text-7xl">What's trending</h1>
        <div className="text-center text-white mt-10 md:mt-16 max-w-screen-lg mx-auto md:text-base text-sm relative">
          <p>
            Lorem ipsum dolor sit amet consectetur adipisicing elit. Consequatur aliquid ullam, illum reprehenderit adipisci quae molestiae ea a aspernatur modi suscipit cupiditate ratione excepturi? Harum dolores voluptatem deserunt sequi veritatis.
          </p>
          <div className="absolute top-3 aspect-video h-32 w-full bg-[#dbaafe38] blur-[120px]"></div>
        </div>
      {/* <Suspense fallback={null}>
        <GetTrendsMainPage />
      </Suspense> */}
      <div className="mt-32 max-w-screen-sm mx-auto flex flex-col gap-10">
        {trendMock.map((trend, index) => (
          <div key={index} className="mt-10">
            <h2 className="text-white text-2xl md:text-4xl text-center font-light">{trend.category}</h2>
            <div className={`grid grid-cols-2 md:grid-cols-${Math.min(trend.topics.length, 3)} gap-3 md:gap-5 mt-5`}>
              {trend.topics.map((topic, index) => (
                <div key={index} className="items-center text-white border border-solid border-zinc-600 p-3 md:p-4 rounded-md bg-white/5 backdrop-blur-[4px]">
                  <p className="bg-gradient-to-b from-[#6d49a6] to-[#ffffff] bg-clip-text text-base md:text-lg text-transparent">{topic.topic}</p>
                  <div>
                    <p className="text-zinc-400 text-sm md:text-base">{topic.memories_count} memories</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      </div>
    </div>
  )
}