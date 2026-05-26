import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { BaseLayoutComponent } from '../../@shared/components/base-layout/base-layout.component';
import { AdminService, AdminUser } from '../../@shared/services/admin.service';
import { AuthService } from '../../@shared/services/auth.service';

@Component({
  selector: 'app-admin-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatIconModule,
    MatTabsModule,
    BaseLayoutComponent
  ],
  templateUrl: './admin-dashboard.component.html',
  styleUrl: './admin-dashboard.component.scss'
})
export class AdminDashboardComponent implements OnInit, OnDestroy {

  activeTab = signal(0);
  deleteConfirmId = signal<number | null>(null);

  // Ingestion history states
  historyLimit = signal(50);
  historyOffset = signal(0);
  historyStatus = signal<string>('all');
  historySearch = signal<string>('');
  expandedJobId = signal<number | null>(null);

  constructor(
    public adminService: AdminService,
    public auth: AuthService
  ) {}

  ngOnInit() {
    this.adminService.startAutoRefresh(15000);
    this.adminService.loadUsers();
  }

  ngOnDestroy() {
    this.adminService.stopAutoRefresh();
  }

  onTabChange(index: number) {
    this.activeTab.set(index);
    if (index === 1) {
      this.adminService.loadUsers();
    } else if (index === 2) {
      this.loadHistory();
    }
  }

  refreshStats() {
    this.adminService.loadStats();
    if (this.activeTab() === 1) {
      this.adminService.loadUsers();
    } else if (this.activeTab() === 2) {
      this.loadHistory();
    }
  }

  loadHistory() {
    this.adminService.loadIngestionHistory(
      this.historyLimit(),
      this.historyOffset(),
      this.historyStatus(),
      this.historySearch()
    );
  }

  onHistoryFilterChange(status: string) {
    this.historyStatus.set(status);
    this.historyOffset.set(0);
    this.loadHistory();
  }

  onHistorySearch() {
    this.historyOffset.set(0);
    this.loadHistory();
  }

  onHistoryPageChange(direction: 'prev' | 'next') {
    const currentOffset = this.historyOffset();
    const limit = this.historyLimit();
    const total = this.adminService.ingestionHistoryCount();
    
    if (direction === 'prev' && currentOffset >= limit) {
      this.historyOffset.set(currentOffset - limit);
      this.loadHistory();
    } else if (direction === 'next' && (currentOffset + limit) < total) {
      this.historyOffset.set(currentOffset + limit);
      this.loadHistory();
    }
  }

  toggleExpandJob(jobId: number) {
    if (this.expandedJobId() === jobId) {
      this.expandedJobId.set(null);
    } else {
      this.expandedJobId.set(jobId);
    }
  }

  getJobStatusClass(status: string): string {
    switch (status) {
      case 'succeeded': return 'job-succeeded';
      case 'failed': return 'job-failed';
      case 'processing': return 'job-processing';
      case 'queued': return 'job-queued';
      default: return '';
    }
  }

  getJobStatusIcon(status: string): string {
    switch (status) {
      case 'succeeded': return 'check_circle';
      case 'failed': return 'error';
      case 'processing': return 'sync';
      case 'queued': return 'schedule';
      default: return 'help';
    }
  }

  changeRole(user: AdminUser, newRole: string) {
    this.adminService.updateUserRole(user.id, newRole).subscribe({
      error: (err) => alert(err.error?.error || 'Failed to update role')
    });
  }

  confirmDelete(userId: number) {
    this.deleteConfirmId.set(userId);
  }

  cancelDelete() {
    this.deleteConfirmId.set(null);
  }

  executeDelete(userId: number) {
    this.adminService.deleteUser(userId).subscribe({
      next: () => this.deleteConfirmId.set(null),
      error: (err) => alert(err.error?.error || 'Failed to delete user')
    });
  }

  getStatusClass(status: string): string {
    return status === 'healthy' ? 'status-healthy' : 'status-unhealthy';
  }

  getStatusIcon(status: string): string {
    return status === 'healthy' ? 'check_circle' : 'error';
  }

  getRoleIcon(role: string): string {
    switch (role) {
      case 'admin': return 'shield';
      case 'analyst': return 'analytics';
      case 'viewer': return 'visibility';
      default: return 'person';
    }
  }

  getServiceIcon(service: string): string {
    switch (service) {
      case 'postgresql': return 'storage';
      case 'redis': return 'speed';
      case 'qdrant': return 'hub';
      default: return 'dns';
    }
  }
}
