export type AgentName = 'policy' | 'cluster_operator' | 'dev_team' | 'manual'
export type ScannerUsed = 'checkov' | 'trufflehog' | 'semgrep' | 'k8s_watch' | 'prometheus' | 'manual'
export type Severity = 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO'
export type EventStatus = 'open' | 'remediated' | 'escalated' | 'false_positive'

export interface EvidenceEvent {
  id: string
  created_at: string
  agent_name: AgentName
  scanner_used: ScannerUsed
  check_id: string
  control_id: string
  control_name: string
  resource_name: string
  file_path: string
  severity: Severity
  status: EventStatus
  pr_url: string | null
  violation_description: string
}
