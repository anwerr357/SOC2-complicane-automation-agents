import useSWR from 'swr'
import type { EvidenceEvent } from '../types/evidence'

const fetcher = (url: string) =>
  fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
    return r.json() as Promise<EvidenceEvent[]>
  })

export function useEvidence(limit = 200) {
  const { data, error, isLoading } = useSWR<EvidenceEvent[]>(
    `/evidence?limit=${limit}`,
    fetcher,
    { refreshInterval: 30_000 },
  )
  return { events: data ?? [], error, isLoading }
}

export function useControlEvidence(controlId: string) {
  const { data, error, isLoading } = useSWR<EvidenceEvent[]>(
    `/evidence/${controlId}`,
    fetcher,
    { refreshInterval: 30_000 },
  )
  return { events: data ?? [], error, isLoading }
}
