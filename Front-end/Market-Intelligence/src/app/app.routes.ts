import { Routes } from '@angular/router';

export const routes: Routes = [
    {
    path: '',
    loadComponent: () =>
      import('./Pages/home/home.component').then(
        (m) => m.HomeComponent
      ),
    },
    {
    path: 'reports',
    loadComponent: () =>
      import('./Pages/report-studio/report-studio.component').then(
        (m) => m.ReportStudioComponent
      ),
    },
    {
    path: 'admin',
    loadComponent: () =>
      import('./Pages/admin-dashboard/admin-dashboard.component').then(
        (m) => m.AdminDashboardComponent
      ),
    }
];
