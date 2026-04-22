import axios, { type AxiosResponse } from 'axios'

// 统一响应体 (与后端 com.csg.twinfusion.common.Result 对齐)
export interface ApiResult<T = unknown> {
  code: number
  message: string
  data?: T
}

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' }
})

// 开发阶段:失败响应进 console.error, 生产环境接入统一错误提示.
http.interceptors.response.use(
  (resp: AxiosResponse<ApiResult>) => {
    if (resp.data.code !== 0) {
      console.error('[api]', resp.config.url, resp.data.message)
    }
    return resp
  },
  (err) => {
    console.error('[api] network error', err?.config?.url, err?.message)
    return Promise.reject(err)
  }
)

export default http
