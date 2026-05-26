import { Injectable, signal, Inject, PLATFORM_ID } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { isPlatformBrowser } from '@angular/common';
import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';
import { tap } from 'rxjs';

export interface ServiceHealth {
  status: 'healthy' | 'unhealthy';
  service: string;
  error?: string;
}

export interface QueueStats {
  queued: number;
  active: number;
  failed: number;
  error?: string;
}

export interface CollectionInfo {
  name: string;
  points: number;
  status: string;
}

export interface StorageStats {
  collections: CollectionInfo[];
  total_vectors: number;
  db_size_mb: number;
  error?: string;
}

export interface AdminStats {
  health: {
    postgres: ServiceHealth;
    redis: ServiceHealth;
    qdrant: ServiceHealth;
    timestamp: string;
  };
  queue: QueueStats;
  storage: StorageStats;
  user_count: number;
  timestamp: string;
}

export interface AdminUser {
  id: number;
  email: string;
  display_name: string | null;
  role: 'admin' | 'analyst' | 'viewer';
  created_at: string;
}

export interface IngestionJob {
  id: number;
  task_id: string;
  filename: string;
  original_filename: string | null;
  file_size_kb: number | null;
  department: string;
  source_url: string | null;
  pipeline_type: string | null;
  status: 'queued' | 'processing' | 'succeeded' | 'failed';
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  created_at: string;
}

@Injectable({
  providedIn: 'root'
})
export class AdminService {
  stats = signal<AdminStats | null>(null);
  users = signal<AdminUser[]>([]);
  ingestionHistory = signal<IngestionJob[]>([]);
  ingestionHistoryCount = signal(0);
  loading = signal(false);
  error = signal<string | null>(null);

  private refreshInterval: any = null;

  constructor(
    private http: HttpClient,
    private auth: AuthService,
    @Inject(PLATFORM_ID) private platformId: Object
  ) {}

  loadStats() {
    this.loading.set(true);
    this.error.set(null);
    const headers = this.auth.getAuthHeaders();
    
    this.http.get<AdminStats>(`${environment.apiUrl}/admin/stats`, { headers })
      .subscribe({
        next: (data) => {
          this.stats.set(data);
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set(err.error?.error || 'Failed to load stats');
          this.loading.set(false);
        }
      });
  }

  loadUsers() {
    const headers = this.auth.getAuthHeaders();
    this.http.get<{ users: AdminUser[], total: number }>(`${environment.apiUrl}/admin/users`, { headers })
      .subscribe({
        next: (data) => this.users.set(data.users),
        error: (err) => this.error.set(err.error?.error || 'Failed to load users')
      });
  }

  loadIngestionHistory(limit = 50, offset = 0, status?: string, search?: string) {
    const headers = this.auth.getAuthHeaders();
    let url = `${environment.apiUrl}/admin/ingestion-history?limit=${limit}&offset=${offset}`;
    if (status) url += `&status=${status}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;

    this.http.get<{ history: IngestionJob[], count: number }>(url, { headers })
      .subscribe({
        next: (data) => {
          this.ingestionHistory.set(data.history);
          this.ingestionHistoryCount.set(data.count);
        },
        error: (err) => this.error.set(err.error?.error || 'Failed to load ingestion history')
      });
  }

  updateUserRole(userId: number, role: string) {
    const headers = this.auth.getAuthHeaders();
    return this.http.put<{ success: boolean }>(
      `${environment.apiUrl}/admin/users/${userId}/role`,
      { role },
      { headers }
    ).pipe(
      tap(() => this.loadUsers())
    );
  }

  deleteUser(userId: number) {
    const headers = this.auth.getAuthHeaders();
    return this.http.delete<{ success: boolean }>(
      `${environment.apiUrl}/admin/users/${userId}`,
      { headers }
    ).pipe(
      tap(() => this.loadUsers())
    );
  }

  startAutoRefresh(intervalMs = 15000) {
    if (!isPlatformBrowser(this.platformId)) return;
    this.stopAutoRefresh();
    this.loadStats();
    this.refreshInterval = setInterval(() => this.loadStats(), intervalMs);
  }

  stopAutoRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }
}
