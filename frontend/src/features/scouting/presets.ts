import type { UtilityType } from '../../types/api'
import type { Token } from './ScoutingRadar'
import data from './presets.json'

export interface PresetToken {
  util_type: string
  x: number
  y: number
  w: number
  h: number
  time_from: number
  time_to: number
  support: number
  zone: string | null
}

export interface ScoutingPreset {
  id: string
  map_id: string
  site: string
  label: string
  n_rounds: number
  n_demos: number
  share: number
  lift: number
  tokens: PresetToken[]
}

const UTILS: UtilityType[] = ['smoke', 'flash', 'molotov', 'he']
const byMap = (data as { presets: Record<string, ScoutingPreset[]> }).presets

export const presetsGeneratedAt = (data as { generated_at?: string }).generated_at ?? ''

export const presetsForMap = (mapId: string): ScoutingPreset[] => byMap[mapId] ?? []

export function presetTokens(preset: ScoutingPreset, makeId: () => string): Token[] {
  return preset.tokens
    .filter((tk) => UTILS.includes(tk.util_type as UtilityType))
    .map((tk) => ({
      id: makeId(),
      util_type: tk.util_type as UtilityType,
      time_from: Math.round(tk.time_from),
      time_to: Math.round(tk.time_to),
      x: Math.round(tk.x),
      y: Math.round(tk.y),
      w: Math.round(tk.w),
      h: Math.round(tk.h),
    }))
}
