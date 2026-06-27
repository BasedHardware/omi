'use client'

import { REGIONS, COUNTRY_NAMES } from '@/types/distributor'

interface CountryPickerProps {
  selectedCountries: string[]
  onChange: (countries: string[]) => void
  disabled?: boolean
}

export default function CountryPicker({ selectedCountries, onChange, disabled }: CountryPickerProps) {
  const isRegionFullySelected = (regionCountries: readonly string[]) =>
    regionCountries.every((c) => selectedCountries.includes(c))

  const isRegionPartiallySelected = (regionCountries: readonly string[]) =>
    regionCountries.some((c) => selectedCountries.includes(c)) && !isRegionFullySelected(regionCountries)

  const toggleRegion = (regionCountries: readonly string[]) => {
    if (disabled) return
    if (isRegionFullySelected(regionCountries)) {
      onChange(selectedCountries.filter((c) => !regionCountries.includes(c)))
    } else {
      const merged = new Set([...selectedCountries, ...regionCountries])
      onChange(Array.from(merged))
    }
  }

  const toggleCountry = (code: string) => {
    if (disabled) return
    if (selectedCountries.includes(code)) {
      onChange(selectedCountries.filter((c) => c !== code))
    } else {
      onChange([...selectedCountries, code])
    }
  }

  return (
    <div className="space-y-3 max-h-64 overflow-y-auto border rounded-md p-3">
      {REGIONS.map((region) => (
        <div key={region.code}>
          <label className="flex items-center gap-2 cursor-pointer font-medium text-sm mb-1">
            <input
              type="checkbox"
              checked={isRegionFullySelected(region.countries)}
              ref={(el) => {
                if (el) el.indeterminate = isRegionPartiallySelected(region.countries)
              }}
              onChange={() => toggleRegion(region.countries)}
              disabled={disabled}
              className="rounded border-input"
            />
            {region.name} ({region.code})
          </label>
          <div className="ml-6 flex flex-wrap gap-1">
            {region.countries.map((code) => (
              <label
                key={code}
                className="flex items-center gap-1 cursor-pointer text-xs px-1.5 py-0.5 rounded hover:bg-muted"
                title={COUNTRY_NAMES[code]}
              >
                <input
                  type="checkbox"
                  checked={selectedCountries.includes(code)}
                  onChange={() => toggleCountry(code)}
                  disabled={disabled}
                  className="rounded border-input h-3 w-3"
                />
                {code}
              </label>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
