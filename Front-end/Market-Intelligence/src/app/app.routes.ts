import { Routes } from '@angular/router';

export const routes: Routes = [
    {
    path: '',
    loadComponent: () =>
      import('./Pages/home/home.component').then(
        (m) => m.HomeComponent
      ),
  }
];
