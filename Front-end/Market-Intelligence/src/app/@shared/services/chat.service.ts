import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '@environments/environment';
import { AuthService } from './auth.service';
import { tap, map, of } from 'rxjs';

export interface ChatSession {
    id: number;
    title: string;
    created_at: string;
    updated_at: string;
}

export interface ChatMessage {
    id?: number;
    role: 'user' | 'assistant';
    content: string;
    execution_time?: number;
    created_at?: string;
}

@Injectable({
    providedIn: 'root'
})
export class ChatService {
    sessions = signal<ChatSession[]>([]);
    currentSessionId = signal<number | null>(null);

    constructor(private http: HttpClient, private auth: AuthService) { }

    private getHeaders() {
        return {
            'Authorization': `Bearer ${this.auth.getToken()}`
        };
    }

    loadSessions() {
        if (!this.auth.isAuthenticated()) return of([]);

        return this.http.get<{ sessions: ChatSession[] }>(`${environment.apiUrl}/chats`, {
            headers: this.getHeaders()
        }).pipe(
            map(res => res.sessions),
            tap(sessions => this.sessions.set(sessions))
        );
    }

    createSession(title: string = 'New Chat') {
        if (!this.auth.isAuthenticated()) {
            // For guests, we don't save to backend
            this.currentSessionId.set(null);
            return of({ session_id: null });
        }

        return this.http.post<{ session_id: number }>(`${environment.apiUrl}/chats`, { title }, {
            headers: this.getHeaders()
        }).pipe(
            tap(res => {
                this.currentSessionId.set(res.session_id);
                this.loadSessions().subscribe();
            })
        );
    }

    getChatDetails(sessionId: number) {
        return this.http.get<{ session: ChatSession, messages: ChatMessage[] }>(`${environment.apiUrl}/chats/${sessionId}`, {
            headers: this.getHeaders()
        }).pipe(
            tap(() => this.currentSessionId.set(sessionId))
        );
    }

    renameChat(sessionId: number, title: string) {
        return this.http.put(`${environment.apiUrl}/chats/${sessionId}/rename`, { title }, {
            headers: this.getHeaders()
        }).pipe(
            tap(() => this.loadSessions().subscribe())
        );
    }

    deleteChat(sessionId: number) {
        return this.http.delete(`${environment.apiUrl}/chats/${sessionId}`, {
            headers: this.getHeaders()
        }).pipe(
            tap(() => {
                if (this.currentSessionId() === sessionId) {
                    this.currentSessionId.set(null);
                }
                this.loadSessions().subscribe();
            })
        );
    }
}
