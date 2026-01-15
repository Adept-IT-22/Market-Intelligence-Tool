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
    { "name": "Start New Chat", "icon": "add_comment", "route": "/" }
  ]

  isExpanded: boolean = true;

  toggleSidebar() {
    this.isExpanded = !this.isExpanded;
  }
}
