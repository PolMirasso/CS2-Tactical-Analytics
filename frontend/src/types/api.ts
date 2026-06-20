// TypeScript mirror of the backend pydantic schemas / enums
// (backend/app/domain/schemas.py and enums.py). Keep in sync by hand for now;
// a future step could generate these from the OpenAPI schema.

export type Role = 'user' | 'admin'
export type Visibility = 'private' | 'public'
export type DemoSource = 'upload' | 'hltv'
export type DemoStatus = 'pending' | 'parsed' | 'failed'
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed'
export type DateRange =
  | 'last_month'
  | 'last_3_months'
  | 'last_6_months'
  | 'last_12_months'
export type UtilityType = 'smoke' | 'flash' | 'molotov' | 'he'
export type Region = 'A' | 'B' | 'Mid'
export type Site = 'A' | 'B' | 'Mid' | 'NoPlant'
export type BuyType = 'eco' | 'force' | 'full'

export interface UserOut {
  id: number
  email: string
  role: Role
  created_at: string
}

export interface Token {
  access_token: string
  token_type: string
}

export interface DemoOut {
  id: number
  owner_id: number
  source: DemoSource
  status: DemoStatus
  visibility: Visibility
  map_id: string | null
  team: string | null
  opponent: string | null
  event: string | null
  match_date: string | null
  size_bytes: number | null
  error: string | null
  created_at: string
}

export interface UploadResult {
  demo: DemoOut
  rounds: number
  utility_events: number
}

export interface UtilityEventOut {
  id: number
  util_type: UtilityType
  zone: string | null
  region: Region | null
  round_time_s: number
  team: string | null
}

export interface RoundOut {
  id: number
  round_number: number
  map_id: string
  team: string | null
  opponent: string | null
  buy_type: BuyType
  equip_value: number
  target_site: Site
  utility: UtilityEventOut[]
}

export interface DemoAnalysisOut {
  demo: DemoOut
  rounds: RoundOut[]
}

export interface TeamHit {
  id: string
  name: string
  url: string
  logo: string | null
}

export interface DownloadJobOut {
  id: string
  status: JobStatus
  team_id: string
  team_name: string | null
  map_id: string | null
  date_range: string
  visibility: Visibility
  matches: number
  demos_ingested: number
  demo_ids: number[]
  error: string | null
  created_at: string
  updated_at: string
}

export interface DownloadDemosIn {
  team_id: string
  team_name?: string | null
  map_id?: string | null
  date_range?: DateRange
  visibility?: Visibility
}

export interface ZoneOut {
  id: string
  name: string
  region: Region
  centroid: [number, number]
}

export interface MapCalibration {
  // World→radar-pixel: px = (x - pos_x) / scale, py = (pos_y - y) / scale
  pos_x: number
  pos_y: number
  scale: number
}

export interface MapOut {
  id: string
  name: string
  zones: ZoneOut[]
  has_radar: boolean
  calibration: MapCalibration | null
}

// 2D replay
export interface ReplayRoundMeta {
  round_number: number
  duration_s: number
  n_frames: number
  n_players: number
  n_utility: number
  winner: string | null
}

export interface ReplayMetaOut {
  demo_id: number
  map_id: string
  sample_hz: number
  rounds: ReplayRoundMeta[]
  has_radar: boolean
  calibration: MapCalibration | null
}

export interface ReplayPlayer {
  steamid: string
  name: string
  side: 't' | 'ct'
}

export interface ReplayFrame {
  t: number
  // One [x, y, yaw, hp] per player, aligned to the round roster order.
  pos: [number, number, number, number][]
  // Per player: [armor, money, weaponIdx, clipAmmo, reserveAmmo, nadeMask].
  // weaponIdx indexes ReplayRound.weapons; nadeMask packs grenade types held.
  st: number[][]
}

export interface ReplayUtility {
  type: UtilityType
  side: string
  t: number
  from: [number, number]
  to: [number, number]
}

export interface ReplayBomb {
  t: number // seconds since freeze end when planted
  x: number
  y: number
  site: string | null
}

export interface ReplayKill {
  t: number
  atk: string // attacker name
  as: string // attacker side ("t" | "ct")
  vic: string // victim name
  vs: string // victim side
  wp: string // weapon
  hs: boolean // headshot
}

export interface ReplayRound {
  round_number: number
  duration_s: number
  players: ReplayPlayer[]
  // Weapon-name table indexed by ReplayFrame.st weapon indices (0 = none).
  weapons: string[]
  // Shot events as [playerIdx, t]; drives the firing/muzzle-flash indicator.
  fires: [number, number][]
  // Bomb plant for the round (world-space), or null if never planted.
  bomb: ReplayBomb | null
  // Kill events for the kill feed.
  kills: ReplayKill[]
  frames: ReplayFrame[]
  utility: ReplayUtility[]
}

export interface GroupOut {
  id: number
  name: string
  owner_id: number
  member_count: number
  is_owner: boolean
}

export interface InvitationOut {
  id: number
  group_id: number
  group_name: string
  inviter_email: string
  status: string
  created_at: string
}
