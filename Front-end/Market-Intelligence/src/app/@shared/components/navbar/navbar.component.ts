import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ThemeService } from '../../services/theme.service';
import { MatIconModule } from '@angular/material/icon';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../services/auth.service';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { AuthModalComponent } from '../auth-modal/auth-modal.component';
import { MatMenuModule } from '@angular/material/menu';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-navbar',
  standalone: true,
  imports: [RouterLink, MatIconModule, CommonModule, MatDialogModule, MatMenuModule, MatButtonModule],
  templateUrl: './navbar.component.html',
  styleUrl: './navbar.component.scss'
})
export class NavbarComponent {
  constructor(
    public themeService: ThemeService,
    public auth: AuthService,
    private dialog: MatDialog
  ) { }

  toggleTheme() {
    this.themeService.toggleTheme();
  }

  openLogin() {
    this.dialog.open(AuthModalComponent, {
      width: '450px',
      panelClass: 'auth-dialog'
    });
  }

  logout() {
    this.auth.logout();
    window.location.reload(); // Refresh to clear states
  }

  getUserDisplayName(): string {
    const user = this.auth.currentUser();
    if (user?.displayName) return user.displayName;
    if (user?.email) return user.email.split('@')[0];
    return 'Research User';
  }

  getUserInitial(): string {
    const name = this.getUserDisplayName();
    return (name[0] || 'U').toUpperCase();
  }
}
