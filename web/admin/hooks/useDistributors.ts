import { useState, useEffect } from 'react'
import { Distributor, ShopifyLocation } from '@/types/distributor'
import { useAuthFetch } from '@/hooks/useAuthToken'

export interface CreateDistributorData {
  email: string
  name: string
  isActive: boolean
  isAdmin: boolean
  countries: string[]
  locationId: string
  locationName: string
}

export interface UpdateDistributorData extends Partial<CreateDistributorData> {
  id: string
}

export const useDistributors = () => {
  const [distributors, setDistributors] = useState<Distributor[]>([])
  const [locations, setLocations] = useState<ShopifyLocation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { fetchWithAuth, token } = useAuthFetch()

  const fetchDistributors = async () => {
    if (!token) return
    try {
      setLoading(true)
      setError(null)

      const [distRes, locRes] = await Promise.all([
        fetchWithAuth('/api/distributors'),
        fetchWithAuth('/api/distributors/locations'),
      ])

      if (!distRes.ok) throw new Error('Failed to fetch distributors')

      const distData = await distRes.json()
      setDistributors(distData.distributors || [])

      // Locations may fail if Shopify isn't configured - don't block on it
      if (locRes.ok) {
        const locData = await locRes.json()
        setLocations(locData.locations || [])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  const createDistributor = async (data: CreateDistributorData) => {
    try {
      setError(null)
      const response = await fetchWithAuth('/api/distributors', {
        method: 'POST',
        body: JSON.stringify(data),
      })

      const result = await response.json()
      if (!response.ok) {
        throw new Error(result.error || 'Failed to create distributor')
      }

      await fetchDistributors()
      return result.distributor
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'An error occurred'
      setError(msg)
      throw new Error(msg)
    }
  }

  const updateDistributor = async (data: UpdateDistributorData) => {
    try {
      setError(null)
      const response = await fetchWithAuth('/api/distributors', {
        method: 'PUT',
        body: JSON.stringify(data),
      })

      const result = await response.json()
      if (!response.ok) {
        throw new Error(result.error || 'Failed to update distributor')
      }

      await fetchDistributors()
      return result.distributor
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'An error occurred'
      setError(msg)
      throw new Error(msg)
    }
  }

  useEffect(() => {
    if (token) {
      fetchDistributors()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  return {
    distributors,
    locations,
    loading,
    error,
    fetchDistributors,
    createDistributor,
    updateDistributor,
  }
}
