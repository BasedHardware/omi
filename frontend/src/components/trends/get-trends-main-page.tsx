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

    acc[category][type === 'best' ? 'best' : 'worst'] = [
      ...acc[category][type === 'best' ? 'best' : 'worst'],
      ...topics,
    ];

    return acc;
  }, {});

  return (
    <div className="mx-auto mt-20 max-w-screen-md space-y-8">
      {Object.keys(groupedTrends).map((category) => (
        <div key={category} className="">
          <h2 className="text-start text-2xl font-semibold text-[#03234d] md:text-3xl bg-[#04e1cb] py-3 rounded-t-lg px-3">
            {categories['category'] ?? capitalizeFirstLetter(category)}
          </h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 border border-solid border-gray-100 p-3 bg-white rounded-b-lg">
            {groupedTrends[category].best.length > 0 && (
              <div>
                <h3 className="mb-2 text-lg font-semibold">
                  <ArrowUpCircle className="mr-1 inline-block text-sm text-green-500" />
                  Best {categories[category]}
                </h3>
                <ul className="flex flex-col gap-2">
                  {groupedTrends[category].best.map((topic, index) => (
                    <li key={topic.id} className={`flex items-center text-base md:text-lg rounded-md p-2`}>
                      {index < 3 && (
                        <span
                          className={`mr-2 flex h-5 w-5 items-center justify-center rounded-md p-0.5 text-xs font-bold ${
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
                      {topic.topic}
                      {topic.memories_count} {topic.memories_count === 1 ? 'Conversartion' : 'Conversations'}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {groupedTrends[category].worst.length > 0 && (
              <div>
                <h3 className="mb-2 text-lg font-semibold">
                  <ArrowDownCircle className="mr-1 inline-block text-sm text-red-500" />
                  Worst {categories[category]}
                </h3>
                <ul className="">
                  {groupedTrends[category].worst.map((topic, index) => (
                    <li key={topic.id} className={`flex items-center text-base md:text-lg rounded-md p-2`}>
                      {index < 3 && (
                        <span
                          className={`mr-2 flex h-5 w-5 items-center justify-center rounded-md p-0.5 text-xs font-bold ${
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
                      {topic.topic}
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
