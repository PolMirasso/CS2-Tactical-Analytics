// TypeScript mirror of the backend pydantic schemas / enums
// (backend/app/domain/schemas.py and enums.py). Keep in sync by hand for now;
// a future step could generate these from the OpenAPI schema.

export type Role = 'user' | 'admin'
export type Visibility = 'private' | 'public'
export type DemoSource = 'upload' | 'hltv'
export type DemoStatus = 'pending' | 'parsed' | 'failed'
export type JobStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'cancelling'
  | 'completed'
  | 'failed'
  | 'cancelled'
export type DateRange =
  | 'last_month'
  | 'last_3_months'
  | 'last_6_months'
  | 'last_12_months'
export type UtilityType = 'smoke' | 'flash' | 'molotov' | 'he'
export type Region = 'A' | 'B' | 'Mid'
export type Site = 'A' | 'B' | 'Mid' | 'NoPlant'
export type BuyType =
  | 'pistol'
  | 'full_eco'
  | 'eco'
  | 'ak_hero'
  | 'm4_hero'
  | 'awp_hero'
  | 'force'
  | 'full'

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
  team_hltv_id: string | null
  opponent_hltv_id: string | null
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
  duplicate: boolean
}

export interface ReparseStatus {
  running: boolean
  total: number
  done: number
  ok: number
  failed: number
  map_id: string | null
  started_at: string | null
  finished_at: string | null
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
  winner: string | null
  win_reason: string | null
  utility: UtilityEventOut[]
}

export interface PlayerStatOut {
  name: string
  team: string | null
  kills: number
  deaths: number
  assists: number
  headshots: number
  rounds: number
  adr: number | null
}

export interface DemoAnalysisOut {
  demo: DemoOut
  rounds: RoundOut[]
  players: PlayerStatOut[]
}

export interface DemoListOut {
  items: DemoOut[]
  total: number
}

export interface DemoListParams {
  map_id?: string
  team?: string
  date_from?: string
  date_to?: string
  limit?: number
  offset?: number
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
  matches_total: number
  demos_ingested: number
  demos_total: number
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
  max_matches?: number
}

// analytics (aggregated historical insights)
export interface SiteStat {
  site: Site
  rounds: number
  pct: number
  wins: number
  win_rate: number
}

export interface SiteDistributionOut {
  map_id: string
  team: string | null
  total_rounds: number
  total_demos: number
  overall_win_rate: number
  sites: SiteStat[]
}

export interface SiteDistributionParams {
  map_id: string
  team?: string
  buy_type?: BuyType[]
  date_from?: string
  date_to?: string
}

export interface RosterEntry {
  demo_id: number
  match_date: string | null
  opponent: string | null
  players: string[]
  added: string[]
  removed: string[]
  complete: boolean
}

export interface TeamRostersOut {
  map_id: string
  team: string | null
  has_changes: boolean
  n_demos: number
  core: string[]
  entries: RosterEntry[]
}

// scouting / site prediction (ML)
export interface UtilityInput {
  util_type: UtilityType
  zone?: string | null
  region?: Region | null
  // drawn position in 1024-space radar pixels (deepsets)
  x?: number
  y?: number
  // drawn box size
  w?: number
  h?: number
  time_from?: number
  time_to?: number
  round_time_s?: number
  side: string
}

export interface PredictIn {
  map_id: string
  team?: string | null
  opponent?: string | null
  buy_type: BuyType
  equip_value?: number
  utility: UtilityInput[]
}

export interface SiteProb {
  site: Site
  prob: number
}

export interface PredictOut {
  map_id: string
  team: string | null
  predicted_site: Site
  confidence: number
  source: 'model' | 'baseline'
  sites: SiteProb[]
  baseline: SiteProb[]
}

export interface ZoneUtilStat {
  zone: string
  region: Region | null
  smoke: number
  flash: number
  molotov: number
  he: number
  total: number
}

export interface TendenciesOut {
  map_id: string
  team: string | null
  total_rounds: number
  sites: SiteStat[]
  heatmap: ZoneUtilStat[]
}

export interface ReliabilityBin {
  confidence: number
  accuracy: number
  count: number
}

export interface PerMapMetric {
  map_id: string
  n_rounds: number
  n_plant: number
  accuracy: number | null
  site_accuracy: number | null
  baseline_accuracy: number | null
}

export interface ModelStatusOut {
  trained: boolean
  trained_at: string | null
  n_rounds: number
  n_teams: number
  classes: string[]
  accuracy: number | null
  site_accuracy: number | null
  baseline_accuracy: number | null
  // calibration (temperature scaling): ECE after vs. before + diagram bins
  ece: number | null
  ece_uncalibrated: number | null
  reliability?: ReliabilityBin[] | null
  per_map?: PerMapMetric[] | null
  //gate mean site alpha pooling gate_T site_T
  params?: Record<string, string> | null
}

export interface ZoneOut {
  id: string
  name: string
  region: Region
  centroid: [number, number]
  bounds: [number, number, number, number]
  polygon?: [number, number][] | null
}

export interface MapCalibration {
  // World→radar-pixel: px = (x - pos_x) / scale, py = (pos_y - y) / scale
  pos_x: number
  pos_y: number
  scale: number
  // Two-level maps (nuke): points below lower_level_max_units (world z) use `lower`.
  lower?: MapCalibration | null
  lower_level_max_units?: number | null
}

export interface MapOut {
  id: string
  name: string
  zones: ZoneOut[]
  has_radar: boolean
  has_data: boolean
  calibration: MapCalibration | null
}

export interface TeamRef {
  id: string
  name: string
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

export interface BombDamageSite {
  label: string // "A" | "B"
  center: [number, number, number] // world [x, y, z]
  dmg: number[] // 256-entry PNG-gray -> HP lookup table
}

export interface BombDamageMeta {
  // C4 shockwave-damage grid
  w: number
  h: number
  scale: number
  origin: [number, number]
  // Two-level maps
  has_lower?: boolean
  sites: BombDamageSite[]
}

export interface ReplayMetaOut {
  demo_id: number
  map_id: string
  sample_hz: number
  rounds: ReplayRoundMeta[]
  has_radar: boolean
  calibration: MapCalibration | null
  bomb_damage?: BombDamageMeta | null
}

export interface ReplayPlayer {
  steamid: string
  name: string
  side: 't' | 'ct'
  ci?: number // teammate-colour index
}

export interface ReplayFrame {
  t: number
  // One [x, y, yaw, hp, z] per player, aligned to the round roster order.
  pos: [number, number, number, number, number][]
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
  z?: number
  path?: [number, number, number][]
}

export interface ReplayBomb {
  t: number // seconds since freeze end when planted
  x: number
  y: number
  z?: number | null
  site: string | null
  // Detonation (seconds since freeze end)
  expl?: number | null
}

export interface ReplayKill {
  t: number
  atk: string // attacker name
  as: string // attacker side ("t" | "ct")
  vic: string // victim name
  vs: string // victim side
  wp: string // weapon
  hs: boolean // headshot
  air?: boolean // attacker jumping 
  ns?: boolean // no-scope kill
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
