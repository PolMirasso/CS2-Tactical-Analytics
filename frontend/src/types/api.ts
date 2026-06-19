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

export interface MapOut {
  id: string
  name: string
  zones: ZoneOut[]
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
