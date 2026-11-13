export type VehicleType = 'CAR' | 'MOTO' | 'UNKNOWN'
export type LaneDirection = 'IN' | 'OUT'
export type LaneVehicleTypes = 'CAR' | 'MOTO' | 'BOTH'

export interface User {
  id: number
  username: string
  display_name: string
  is_active: boolean
  created_at: string
}

export interface ResidentVehicle {
  id: number
  household_id: number
  household_unit: string
  plate: string
  plate_display: string
  vehicle_type: 'CAR' | 'MOTO'
  valid_from: string | null
  valid_until: string | null
  is_active: boolean
  note: string
  created_at: string
}

export interface Household {
  id: number
  unit_no: string
  owner_name: string
  phone: string
  note: string
  created_at: string
  vehicle_count: number
  vehicles?: ResidentVehicle[]
}

export interface Visitor {
  id: number
  household_id: number
  household_unit: string
  name: string
  phone: string
  plate: string
  plate_display: string
  vehicle_type: 'CAR' | 'MOTO'
  purpose: string
  authorized_from: string
  authorized_until: string
  status: 'RESERVED' | 'ENTERED' | 'EXITED' | 'OVERSTAY' | 'CANCELLED'
  source: 'RESERVATION' | 'WALK_IN'
  entered_at: string | null
  exited_at: string | null
  created_at: string
}

export interface BlacklistEntry {
  id: number
  plate: string
  plate_display: string
  vehicle_type: VehicleType
  reason: string
  is_active: boolean
  created_at: string
}

export interface LaneStatus {
  online: boolean
  last_error?: string
  capture_fps?: number
  last_plate?: string
  last_plate_at?: number | null
}

export interface Lane {
  id: number
  name: string
  direction: LaneDirection
  source_url: string
  vehicle_types: LaneVehicleTypes
  gate_driver: 'simulated' | 'http_relay' | 'modbus'
  gate_config: Record<string, unknown>
  auto_allow_unknown: boolean
  enabled: boolean
  status: LaneStatus
}

export interface AccessEvent {
  id: number
  lane_id: number | null
  lane_name: string
  direction: LaneDirection
  plate: string
  plate_display: string
  vehicle_type: VehicleType
  confidence: number
  category: 'RESIDENT' | 'VISITOR' | 'BLACKLIST' | 'UNKNOWN' | 'MANUAL'
  decision: 'AUTO_ALLOW' | 'MANUAL_ALLOW' | 'DENY' | 'PENDING'
  household_unit: string
  ref_vehicle_id: number | null
  ref_visitor_id: number | null
  operator_name: string
  note: string
  snapshot_url: string
  plate_crop_url: string
  occurred_at: string
  decided_at: string | null
}

export interface AlertItem {
  id: number
  type: 'BLACKLIST' | 'UNKNOWN_VEHICLE' | 'OVERSTAY' | 'CAMERA_OFFLINE' | 'GATE_ERROR'
  plate: string
  plate_display: string
  event_id: number | null
  visitor_id: number | null
  lane_id: number | null
  message: string
  acknowledged: boolean
  acknowledged_by: number | null
  acknowledged_at: string | null
  created_at: string
}

export interface DashboardStats {
  today_in: number
  today_out: number
  today_denied: number
  pending: number
  onsite_vehicles: number
  onsite_visitors: number
  overstay_visitors: number
  unack_alerts: number
}

export interface PresenceItem {
  id: number
  plate: string
  plate_display: string
  entered_at: string
  category: string
  household_unit: string
  vehicle_type: string
  is_resident: boolean
}

export interface SettingMeta {
  key: string
  default: unknown
  type: 'str' | 'int' | 'float' | 'bool'
  description: string
  min: number | null
  max: number | null
}

export interface SettingsResponse {
  values: Record<string, unknown>
  meta: SettingMeta[]
}

export const CATEGORY_LABEL: Record<string, string> = {
  RESIDENT: '住戶',
  VISITOR: '訪客',
  BLACKLIST: '黑名單',
  UNKNOWN: '未登記',
  MANUAL: '手動開閘',
}

export const DECISION_LABEL: Record<string, string> = {
  AUTO_ALLOW: '自動放行',
  MANUAL_ALLOW: '人工放行',
  DENY: '拒絕',
  PENDING: '待處理',
}

export const DIRECTION_LABEL: Record<string, string> = {
  IN: '進場',
  OUT: '離場',
}

export const VEHICLE_TYPE_LABEL: Record<string, string> = {
  CAR: '汽車',
  MOTO: '機車',
  UNKNOWN: '未知',
  BOTH: '汽機車皆可',
}

export const VISITOR_STATUS_LABEL: Record<string, string> = {
  RESERVED: '已預約',
  ENTERED: '已入場',
  EXITED: '已離場',
  OVERSTAY: '逾時未離場',
  CANCELLED: '已取消',
}

export const ALERT_TYPE_LABEL: Record<string, string> = {
  BLACKLIST: '黑名單警示',
  UNKNOWN_VEHICLE: '未登記車輛',
  OVERSTAY: '訪客逾時',
  CAMERA_OFFLINE: '攝影機離線',
  GATE_ERROR: '柵欄異常',
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await fetch(path, { credentials: 'same-origin', ...init, headers })
  if (res.status === 401 && !path.startsWith('/api/auth/login') && !path.startsWith('/api/public/')) {
    onUnauthorized?.()
  }
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const data = await res.json()
      if (typeof data?.detail === 'string') msg = data.detail
      else if (Array.isArray(data?.detail)) msg = data.detail.map((d: { msg?: string }) => d.msg).join('；')
    } catch {
      // ignore
    }
    throw new ApiError(res.status, msg)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body === undefined ? undefined : JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form }),
}

export function fmtDateTime(val: string | null | undefined): string {
  if (!val) return '—'
  return val.replace('T', ' ').slice(0, 19)
}

export function toLocalIso(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
