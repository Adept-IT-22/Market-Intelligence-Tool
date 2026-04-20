import { NgClass, NgFor, NgIf, DatePipe } from '@angular/common';
import { Component, OnInit, signal, ViewChild, ElementRef } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../services/auth.service';
import { ChatService, ChatSession } from '../../services/chat.service';
import { MatMenuModule } from '@angular/material/menu';
import { FormsModule } from '@angular/forms';

import { UiService } from '../../services/ui.service';

import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-sidebar',
  imports: [MatIconModule, NgFor, NgClass, NgIf, MatMenuModule, FormsModule, DatePipe, RouterLink],
  templateUrl: './sidebar.component.html',
  styleUrl: './sidebar.component.scss'
})
export class SidebarComponent implements OnInit {
  editingSessionId = signal<number | null>(null);
  editTitle = '';

  @ViewChild('editInput') set editInput(element: ElementRef<HTMLInputElement>) {
    if (element) {
      element.nativeElement.focus();
      element.nativeElement.select();
    }
  }

  constructor(
    public auth: AuthService,
    public chatService: ChatService,
    public uiService: UiService
  ) { }

  ngOnInit() {
    // Sessions are now loaded automatically by ChatService when authenticated
  }

  toggleSidebar() {
    this.uiService.toggleSidebar();
  }

  createNewChat() {
    this.chatService.createSession().subscribe(() => {
      // Handle UI update if needed, but signal should handle it
    });
  }

  selectChat(session: ChatSession) {
    // Only select if not editing
    if (this.editingSessionId() !== session.id) {
      this.chatService.getChatDetails(session.id).subscribe();
    }
  }

  startEditing(session: ChatSession, event: Event) {
    event.stopPropagation();
    this.editingSessionId.set(session.id);
    this.editTitle = session.title;
  }

  saveRename(session: ChatSession) {
    const newTitle = this.editTitle.trim();
    if (newTitle && newTitle !== session.title) {
      this.chatService.renameChat(session.id, newTitle).subscribe();
    }
    this.editingSessionId.set(null);
  }

  cancelEditing() {
    this.editingSessionId.set(null);
  }

  deleteChat(session: ChatSession, event: Event) {
    event.stopPropagation();
    if (confirm(`Are you sure you want to delete "${session.title}"?`)) {
      this.chatService.deleteChat(session.id).subscribe();
    }
  }
}
