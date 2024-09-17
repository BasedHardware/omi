import getTrends from '@/src/actions/trends/get-trends';
import capitalizeFirstLetter from '@/src/utils/capitalize-first-letter';
import { ArrowDownCircle, ArrowUpCircle } from 'iconoir-react';

const categories = {
  ceo: 'CEOs',
  ai_product: 'AI Products',
  industry: 'Industries',
  innovation: 'Innovations',
  company: 'Companies',
  research: 'Research',
  product: 'Products',
  event: 'Events',
  hardware_product: 'Hardware Products',
  software_product: 'Software Products',
};

export default async function GetTrendsMainPage() {
  const trends = await getTrends();
  if (!trends) return null;

  // Agrupar trends por categoría
  const groupedTrends = trends.reduce((acc, trend) => {
    const { category, type, topics } = trend;

    if (!acc[category]) acc[category] = { best: [], worst: [] };

    const topicsToPush = type === 'best' ? 'best' : 'worst';
    acc[category][topicsToPush] = [
      ...acc[category][topicsToPush],
      ...topics,
    ].slice(0, 6); // Limit to max 6

    return acc;
  }, {});

  return (
    <div className="mx-auto mt-20 max-w-screen-md space-y-8">
      {Object.keys(groupedTrends).map((category) => (
        <div key={category} className="">
          <h2 className="text-start text-2xl font-semibold text-[#03234d] md:text-3xl bg-[#04e1cb] py-3 rounded-t-lg px-3">
            {categories['category'] ?? capitalizeFirstLetter(category)}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 pt-3 pb-6 border border-solid border-gray-100 bg-white rounded-b-lg divide-x">
            {groupedTrends[category].best.length > 0 && (
              <div className='px-3'>
                <h3 className="mb-2 text-base py-3 sticky top-16 md:top-0 bg-white z-10">
                  <ArrowUpCircle className="mr-1 inline-block text-sm text-green-500" />
                  Best {categories[category]}
                </h3>
                <ul className="flex flex-col gap-5">
                  {groupedTrends[category].best.map((topic, index) => (
                    <li key={topic.id} className={`flex items-start justify-start text-base md:text-lg rounded-md relative border border-solid ${
                            index === 0
                              ? 'border-amber-300 bg-gradient-to-r to-yellow-100/80 from-white'
                              : index === 1
                              ? 'border-gray-500 '
                              : 'border-gray-300'
                          }`}>
                      {index < 3 && (
                        <span
                          className={`flex h-5 rounded-sm items-center justify-center p-0.5 text-xs font-bold absolute -top-2.5 right-2 px-2 ${
                            index === 0
                              ? 'bg-yellow-400'
                              : index === 1
                              ? 'bg-gray-500 text-white'
                              : 'bg-gray-300'
                          }`}
                        >
                          {index + 1}
                          <sup className="text-[10px]">st</sup>
                        </span>
                      )}
                      <div className='p-2'>
                        <p className='font-semibold'>
                          {capitalizeFirstLetter(topic.topic)}
                        </p>
                        <p className='text-sm text-gray-500'>
                          {topic.memories_count} {topic.memories_count === 1 ? 'Conversartion' : 'Conversations'}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {groupedTrends[category].worst.length > 0 && (
              <div className='px-3'>
                <h3 className="mb-2 text-base py-3 sticky top-16 md:top-0 bg-white z-10">
                  <ArrowDownCircle className="mr-1 inline-block text-sm text-red-500" />
                  Worst {categories[category]}
                </h3>
                <ul className="flex flex-col gap-5">
                  {groupedTrends[category].worst.map((topic, index) => (
                    <li key={topic.id} className={`flex items-start justify-start text-base md:text-lg rounded-md relative border border-solid ${
                            index === 0
                              ? 'border-amber-300 bg-gradient-to-r to-yellow-100/80 from-white'
                              : index === 1
                              ? 'border-gray-500 '
                              : 'border-gray-300'
                          }`}>
                      {index < 3 && (
                              <span
                          className={`flex h-5 rounded-sm items-center justify-center p-0.5 text-xs font-bold absolute -top-2.5 right-2 px-2 ${
                            index === 0
                              ? 'bg-yellow-400'
                              : index === 1
                              ? 'bg-gray-500 text-white'
                              : 'bg-gray-300'
                          }`}
                        >
                          {index + 1}
                          <sup className="text-[10px]">st</sup>
                        </span>
                      )}
                      <div className='p-2'>
                        <p className='font-semibold'>
                          {capitalizeFirstLetter(topic.topic)}
                        </p>
                        <p className='text-sm text-gray-500'>
                          {topic.memories_count} {topic.memories_count === 1 ? 'Conversartion' : 'Conversations'}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
