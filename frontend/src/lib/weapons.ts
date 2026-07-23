// Ids must match the backend catalogue 

export interface WeaponOption {
  id: string
  label: string
}

export interface WeaponCategory {
  id: string
  weapons: WeaponOption[]
}

export const WEAPON_CATEGORIES: WeaponCategory[] = [
  {
    id: 'pistols',
    weapons: [
      { id: 'glock', label: 'Glock-18' },
      { id: 'usp_s', label: 'USP-S' },
      { id: 'p2000', label: 'P2000' },
      { id: 'p250', label: 'P250' },
      { id: 'five_seven', label: 'Five-SeveN' },
      { id: 'tec9', label: 'Tec-9' },
      { id: 'cz75', label: 'CZ75-Auto' },
      { id: 'deagle', label: 'Desert Eagle' },
      { id: 'dualies', label: 'Dual Berettas' },
      { id: 'revolver', label: 'R8 Revolver' },
    ],
  },
  {
    id: 'smgs',
    weapons: [
      { id: 'mac10', label: 'MAC-10' },
      { id: 'mp9', label: 'MP9' },
      { id: 'mp7', label: 'MP7' },
      { id: 'mp5', label: 'MP5-SD' },
      { id: 'ump45', label: 'UMP-45' },
      { id: 'p90', label: 'P90' },
      { id: 'bizon', label: 'PP-Bizon' },
    ],
  },
  {
    id: 'rifles',
    weapons: [
      { id: 'galil', label: 'Galil AR' },
      { id: 'famas', label: 'FAMAS' },
      { id: 'ak47', label: 'AK-47' },
      { id: 'm4a4', label: 'M4A4' },
      { id: 'm4a1_s', label: 'M4A1-S' },
      { id: 'sg553', label: 'SG 553' },
      { id: 'aug', label: 'AUG' },
    ],
  },
  {
    id: 'snipers',
    weapons: [
      { id: 'ssg08', label: 'SSG 08' },
      { id: 'awp', label: 'AWP' },
      { id: 'g3sg1', label: 'G3SG1' },
      { id: 'scar20', label: 'SCAR-20' },
    ],
  },
  {
    id: 'heavy',
    weapons: [
      { id: 'nova', label: 'Nova' },
      { id: 'xm1014', label: 'XM1014' },
      { id: 'mag7', label: 'MAG-7' },
      { id: 'sawedoff', label: 'Sawed-Off' },
      { id: 'm249', label: 'M249' },
      { id: 'negev', label: 'Negev' },
    ],
  },
]

export const WEAPON_IDS: string[] = WEAPON_CATEGORIES.flatMap((c) => c.weapons.map((w) => w.id))

export const WEAPON_LABELS: Record<string, string> = Object.fromEntries(
  WEAPON_CATEGORIES.flatMap((c) => c.weapons.map((w) => [w.id, w.label])),
)
