interface CategorySelectorProps {
  selectedCategory: string;
  setSelectedCategory: (category: string) => void;
}

// Sample categories based on the mobile app
const CATEGORIES = [
  { id: 'productivity-and-organization', name: 'Productivity & Organization' },
  { id: 'education-and-learning', name: 'Education & Learning' },
  { id: 'entertainment', name: 'Entertainment' },
  { id: 'health-and-wellness', name: 'Health & Wellness' },
  { id: 'social-networking', name: 'Social Networking' },
  { id: 'utilities', name: 'Utilities' },
  { id: 'other', name: 'Other' },
];

export default function CategorySelector({
  selectedCategory,
  setSelectedCategory,
}: CategorySelectorProps) {
  return (
    <div className="mb-4">
      <label
        htmlFor="category"
        className="mb-2 block text-sm font-medium text-gray-300"
      >
        Category
      </label>
      <select
        id="category"
        value={selectedCategory}
        onChange={(e) => setSelectedCategory(e.target.value)}
        className="w-full rounded-xl border border-gray-700 bg-gray-800/50 p-2.5 text-white shadow-sm transition-colors focus:border-[#6C8EEF]/50 focus:outline-none focus:ring-1 focus:ring-[#6C8EEF]/50"
        required
      >
        <option value="" disabled>
          Select a category
        </option>
        {CATEGORIES.map((category) => (
          <option key={category.id} value={category.id}>
            {category.name}
          </option>
        ))}
      </select>
    </div>
  );
}
