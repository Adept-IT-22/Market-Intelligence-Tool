import { NgClass, NgFor, NgIf } from '@angular/common';
import { Component } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink, RouterLinkActive } from '@angular/router';

@Component({
  selector: 'app-sidebar',
  imports: [MatIconModule, NgFor, NgClass, RouterLink, RouterLinkActive, NgIf],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.scss'
})
export class SidebarComponent {
  menuItems = [
    { "name": "Home", "icon": "home", "route": "/" },
    { "name": "Analytics", "icon": "insights", "route": "/analytics" },
    { "name": "Projects", "icon": "work_outline", "route": "/projects" },
    { "name": "User Manual", "icon": "menu_book", "route": "/user-manual" }
  ]

  isExpanded: boolean = true;

  toggleSidebar() {
    this.isExpanded = !this.isExpanded;
  }
}
