import { useQuery } from '@tanstack/react-query'
import { mapsApi } from './api'

export function useMaps() {
  return useQuery({
    queryKey: ['maps'],
    queryFn: mapsApi.list,
    staleTime: 5 * 60_000, // map definitions rarely change
  })
}
