import { Component } from '@angular/core';
import { SidebarComponent } from "../sidebar/sidebar.component";
import { NavbarComponent } from "../navbar/navbar.component";
import { UiService } from '../../services/ui.service';
import { NgClass } from '@angular/common';

@Component({
  selector: 'app-base-layout',
  standalone: true,
  imports: [SidebarComponent, NavbarComponent, NgClass],
  templateUrl: './base-layout.component.html',
  styleUrl: './base-layout.component.scss'
})
export class BaseLayoutComponent {
  constructor(public uiService: UiService) { }
}
