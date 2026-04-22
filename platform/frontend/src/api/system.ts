import http, { type ApiResult } from './http'

export interface HealthInfo {
  systemName: string
  status: string
  time: string
}

export interface DomainItem {
  code: string
  name: string
  hasBusinessArchitecture: boolean
  hasDataArchitecture: boolean
  hasApplicationArchitecture: boolean
}

export const getHealth = () =>
  http.get<ApiResult<HealthInfo>>('/health').then((r) => r.data)

export const listDomains = () =>
  http.get<ApiResult<DomainItem[]>>('/domains').then((r) => r.data)
