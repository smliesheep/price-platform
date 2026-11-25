import { cleanParams, del, get, patch, post, type RequestConfig } from '@/api/http'
import type {
  CreateProductPayload,
  PageResult,
  PriceQuery,
  PriceSeries,
  Product,
  ProductQuery,
  Run,
  RunTriggerResult,
  UpdateProductPayload,
} from '@/api/types'

export function getProducts(
  params: ProductQuery = {},
  config?: RequestConfig,
): Promise<PageResult<Product>> {
  return get<PageResult<Product>>('/products', {
    ...config,
    params: cleanParams({ ...params }),
  })
}

export function createProduct(
  payload: CreateProductPayload,
  config?: RequestConfig,
): Promise<Product> {
  return post<Product>('/products', payload, config)
}

export function getProduct(id: number, config?: RequestConfig): Promise<Product> {
  return get<Product>(`/products/${id}`, config)
}

export function updateProduct(
  id: number,
  payload: UpdateProductPayload,
  config?: RequestConfig,
): Promise<Product> {
  return patch<Product>(`/products/${id}`, payload, config)
}

export function deleteProduct(id: number, config?: RequestConfig): Promise<void> {
  return del<void>(`/products/${id}`, config)
}

export function enableProduct(id: number, config?: RequestConfig): Promise<Product> {
  return post<Product>(`/products/${id}/enable`, undefined, config)
}

export function disableProduct(id: number, config?: RequestConfig): Promise<Product> {
  return post<Product>(`/products/${id}/disable`, undefined, config)
}

export function runProduct(id: number, config?: RequestConfig): Promise<RunTriggerResult> {
  return post<RunTriggerResult>(`/products/${id}/run`, undefined, config)
}

export function getProductPrices(
  id: number,
  params: PriceQuery = {},
  config?: RequestConfig,
): Promise<PriceSeries> {
  return get<PriceSeries>(`/products/${id}/prices`, {
    ...config,
    params: cleanParams({ ...params }),
  })
}

export function getProductRuns(
  id: number,
  params: { page?: number; page_size?: number } = {},
  config?: RequestConfig,
): Promise<PageResult<Run>> {
  return get<PageResult<Run>>(`/products/${id}/runs`, {
    ...config,
    params: cleanParams({ ...params }),
  })
}
