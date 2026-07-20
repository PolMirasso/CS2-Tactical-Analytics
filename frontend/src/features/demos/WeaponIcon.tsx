import icons from './weaponIcons.json'

type IconDef = { viewBox: string; paths: { d: string; fillRule?: string; clipRule?: string }[] }
const WEAPON_ICONS = icons as unknown as Record<string, IconDef>

// Strip the `weapon_` prefix and reduce to bare alphanumerics so the many
const norm = (s: string) => s.toLowerCase().replace(/^weapon_/, '').replace(/[^a-z0-9]/g, '')

const NORM_KEYS: Record<string, string> = {}
for (const k of Object.keys(WEAPON_ICONS)) NORM_KEYS[norm(k)] = k

// Display names (demoparser2's `active_weapon_name`) whose normalised form doesn't
const ALIAS: Record<string, string> = {
  usps: 'usp_silencer',
  m4a1s: 'm4a1_silencer',
  m4a4: 'm4a1',
  glock18: 'glock',
  deserteagle: 'deagle',
  cz75auto: 'cz75a',
  p2000: 'hkp2000',
  dualberettas: 'elite',
  r8revolver: 'revolver',
  ppbizon: 'bizon',
  sg553: 'sg556',
  highexplosivegrenade: 'hegrenade',
  incendiarygrenade: 'incgrenade',
  decoygrenade: 'decoy',
  c4explosive: 'c4',
  zeusx27: 'taser',
}

/** Icon key for a weapon name, with a generic-knife fallback for every knife skin. */
function iconKey(weapon: string | undefined): string | null {
  if (!weapon) return null
  const n = norm(weapon)
  if (NORM_KEYS[n]) return NORM_KEYS[n]
  if (ALIAS[n]) return ALIAS[n]
  if (n.includes('knife') || n.includes('bayonet') || n.includes('dagger') || n.includes('karambit')) {
    return 'knife'
  }
  return null
}

/** Whether a glyph exists for this weapon (callers fall back to text if not). */
export const hasWeaponIcon = (weapon: string | undefined): boolean => iconKey(weapon) !== null

export function WeaponIcon({
  weapon,
  title,
  className,
}: {
  weapon: string | undefined
  title?: string
  className?: string
}) {
  const key = iconKey(weapon)
  if (!key) return null
  const icon = WEAPON_ICONS[key]
  return (
    <svg
      viewBox={icon.viewBox}
      className={`fill-current ${className ?? ''}`}
      role="img"
      aria-label={title ?? key}
      preserveAspectRatio="xMidYMid meet"
    >
      {title && <title>{title}</title>}
      {icon.paths.map((p, i) => (
        <path
          key={i}
          d={p.d}
          fillRule={p.fillRule as 'evenodd' | undefined}
          clipRule={p.clipRule as 'evenodd' | undefined}
        />
      ))}
    </svg>
  )
}
