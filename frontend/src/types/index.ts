// types/index.ts - Shared typed contracts consumed by the Trail interface.
export interface User { id: string; email: string; display_name: string; emergency_contact: string; verified: boolean; community_opt_in: boolean }
export interface Contact { id: string; user_id: string; display_name: string; email: string }
export interface Point { latitude: number; longitude: number; speed: number; timestamp: number; marked: boolean }
export interface SafetyEvent { id: string; event_type: string; description: string; severity: string; created_at: number }
export interface Decision { id: string; action: string; explanation: string; mode: string; created_at: number; metrics: {tool?: string; output?: Record<string, unknown>; run_id?: string; tool_calls?: number; elapsed_ms?: number} }
export interface Suggestion { latitude: number; longitude: number; timestamp: number; reasons: string[]; weight: number }
export interface CommunityAlert { id: string; zone_latitude: number; zone_longitude: number; radius_km: number; helper_count: number; accepted_count: number; active: boolean; description: string }
export interface RouteSuggestion { points: [number, number][]; explanation: string; source: string; safe_points: {latitude: number; longitude: number; label: string}[] }
export interface TrailSession {
  id: string; user_id: string; runner_name: string; started_at: number; ended_at: number | null; active: boolean;
  distance: number; current_status: string; share_with: string[]; community_enabled: boolean; is_demo: boolean;
  demo_scenario: string | null; demo_step: number; safety_state: string; checkin_deadline: number | null;
  points: Point[]; route_preview: [number, number][]; events: SafetyEvent[]; decisions: Decision[]; agent_mode: string;
  state: { agent_status?: string; agent_error?: string; risk_score?: number | null; risk_level?: string; seclusion_score?: number | null; anomaly_score?: number;
    stop_duration_seconds?: number; speed?: number; source?: string; last_received_at?: number; suggested_route?: RouteSuggestion };
}
