interface PricingSectionProps {
  isPaid: boolean;
  setIsPaid: (isPaid: boolean) => void;
  price: string;
  setPrice: (price: string) => void;
}

export default function PricingSection({
  isPaid,
  setIsPaid,
  price,
  setPrice,
}: PricingSectionProps) {
  return (
    <div className="mb-4">
      <label className="mb-2 block text-sm font-medium text-gray-300">
        Pricing
      </label>
      <div className="flex space-x-4">
        <div
          className={`cursor-pointer rounded-xl border p-3 text-center text-sm shadow-sm transition-colors hover:border-[#6C8EEF]/50 ${
            !isPaid
              ? 'border-[#6C8EEF] bg-[#6C8EEF]/10 text-[#6C8EEF]'
              : 'border-gray-700 bg-gray-800/50 text-gray-300'
          }`}
          onClick={() => setIsPaid(false)}
          role="radio"
          aria-checked={!isPaid}
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              setIsPaid(false);
            }
          }}
        >
          Free
        </div>
        <div
          className={`cursor-pointer rounded-xl border p-3 text-center text-sm shadow-sm transition-colors hover:border-[#6C8EEF]/50 ${
            isPaid
              ? 'border-[#6C8EEF] bg-[#6C8EEF]/10 text-[#6C8EEF]'
              : 'border-gray-700 bg-gray-800/50 text-gray-300'
          }`}
          onClick={() => setIsPaid(true)}
          role="radio"
          aria-checked={isPaid}
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              setIsPaid(true);
            }
          }}
        >
          Paid
        </div>
      </div>

      {isPaid && (
        <div className="mt-3">
          <label htmlFor="price" className="mb-2 block text-sm font-medium text-gray-300">
            Price (USD)
          </label>
          <input
            type="number"
            id="price"
            min="0.99"
            step="0.50"
            placeholder="e.g. 1.99"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            className="w-full rounded-xl border border-gray-700 bg-gray-800/50 p-2.5 text-white shadow-sm transition-colors focus:border-[#6C8EEF]/50 focus:outline-none focus:ring-1 focus:ring-[#6C8EEF]/50"
          />
          <p className="mt-1 text-xs text-gray-400">
            Minimum price is $0.99. You will receive 70% of the revenue.
          </p>
        </div>
      )}
    </div>
  );
}
