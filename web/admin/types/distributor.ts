export interface Distributor {
  id: string
  email: string
  name: string
  avatarUrl?: string | null
  isActive: boolean
  isAdmin: boolean
  countries: string[]
  locationId?: string | null
  locationName?: string | null
  createdAt: string
  lastLoginAt: string | null
}

export interface ShopifyLocation {
  id: string
  name: string
  isActive: boolean
}

export const REGIONS = [
  {
    code: 'EU',
    name: 'European Union',
    countries: ['DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'PL', 'PT', 'IE', 'GR', 'CZ', 'HU', 'SE', 'DK', 'FI', 'SK', 'BG', 'HR', 'LT', 'SI', 'LV', 'EE', 'CY', 'LU', 'MT', 'RO'],
  },
  {
    code: 'UK',
    name: 'United Kingdom',
    countries: ['GB'],
  },
  {
    code: 'NA',
    name: 'North America',
    countries: ['US', 'CA'],
  },
  {
    code: 'APAC',
    name: 'Asia Pacific',
    countries: ['AU', 'NZ', 'JP', 'KR', 'SG', 'HK', 'TW', 'IN', 'TH', 'MY', 'ID', 'PH', 'VN'],
  },
  {
    code: 'LATAM',
    name: 'Latin America',
    countries: ['MX', 'BR', 'AR', 'CL', 'CO', 'PE'],
  },
  {
    code: 'MENA',
    name: 'Middle East & North Africa',
    countries: ['AE', 'SA', 'IL', 'EG', 'MA'],
  },
]

export const COUNTRY_NAMES: Record<string, string> = {
  DE: 'Germany', FR: 'France', IT: 'Italy', ES: 'Spain', NL: 'Netherlands',
  BE: 'Belgium', AT: 'Austria', PL: 'Poland', PT: 'Portugal', IE: 'Ireland',
  GR: 'Greece', CZ: 'Czech Republic', HU: 'Hungary', SE: 'Sweden', DK: 'Denmark',
  FI: 'Finland', SK: 'Slovakia', BG: 'Bulgaria', HR: 'Croatia', LT: 'Lithuania',
  SI: 'Slovenia', LV: 'Latvia', EE: 'Estonia', CY: 'Cyprus', LU: 'Luxembourg',
  MT: 'Malta', RO: 'Romania', GB: 'United Kingdom', US: 'United States', CA: 'Canada',
  AU: 'Australia', NZ: 'New Zealand', JP: 'Japan', KR: 'South Korea', SG: 'Singapore',
  HK: 'Hong Kong', TW: 'Taiwan', IN: 'India', TH: 'Thailand', MY: 'Malaysia',
  ID: 'Indonesia', PH: 'Philippines', VN: 'Vietnam', MX: 'Mexico', BR: 'Brazil',
  AR: 'Argentina', CL: 'Chile', CO: 'Colombia', PE: 'Peru', AE: 'UAE',
  SA: 'Saudi Arabia', IL: 'Israel', EG: 'Egypt', MA: 'Morocco',
}
