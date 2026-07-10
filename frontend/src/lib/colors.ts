// Shared palette for utility types, map regions and plant sites.
import type { UtilityType } from '@/types/api'

export const UTIL_COLOR: Record<UtilityType, string> = {
  smoke: '#9aa3b2',
  flash: '#f3c244',
  molotov: '#ff7a45',
  he: '#ff5d5d',
}

export const REGION_COLOR: Record<string, string> = {
  A: '#4f8cff',
  B: '#ff5d5d',
  Mid: '#f3c244',
}

export const SITE_COLOR: Record<string, string> = {
  A: '#f59e0b',
  B: '#3b82f6',
  Mid: '#10b981',
  NoPlant: '#6b7280',
}
