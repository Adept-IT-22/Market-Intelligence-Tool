import { NgClass, NgFor } from '@angular/common';
import { Component } from '@angular/core';
import { MatIcon, MatIconModule } from '@angular/material/icon'

@Component({
  selector: 'app-sidebar',
  imports: [MatIcon, NgFor, NgClass],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.scss'
})
export class SidebarComponent {
  menuItems = [
    {"name": "Home", "icon": "home"},
    {"name": "Analytics", "icon": "insights"},
    {"name": "Projects", "icon": "work_outline"},
    {"name": "User Manual", "icon": "menu_book"}
  ]
  
  isExpanded: boolean = false;
  toggleSidebar(){
    this.isExpanded = !this.isExpanded;
  }
}
