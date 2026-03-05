import { Injectable, signal, effect } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';
import { tap, map, of, Observable } from 'rxjs';

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
    private readonly SESSION_KEY = 'mit_current_session_id';


    sessions = signal<ChatSession[]>([]);
    currentSessionId = signal<number | null>(null);

    constructor(private http: HttpClient, private auth: AuthService) {
        // Automatically load sessions
        effect(() => {
            if (this.auth.isAuthenticated()) {
                this.loadSessions().subscribe();
            } else {
                this.loadGuestSessions();
            }
        });
    }

    private loadGuestSessions() {
        this.sessions.set([]);
        this.currentSessionId.set(null);
    }

    private getHeaders() {
        return {
            'Authorization': `Bearer ${this.auth.getToken()}`
        };
    }

    loadSessions() {
        if (!this.auth.isAuthenticated()) {
            this.loadGuestSessions();
            return of(this.sessions());
        }

        return this.http.get<{ sessions: ChatSession[] }>(`${environment.apiUrl}/chats`, {
            headers: this.getHeaders()
        }).pipe(
            map(res => res.sessions.sort((a, b) =>
                new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            )),
            tap(sessions => this.sessions.set(sessions))
        );
    }

    createSession(title: string = 'New Chat'): Observable<any> {
        if (!this.auth.isAuthenticated()) {
            const guestSessions = [...this.sessions()];
            const now = new Date();
            const localTimestamp = now.getFullYear() + '-' +
                String(now.getMonth() + 1).padStart(2, '0') + '-' +
                String(now.getDate()).padStart(2, '0') + ' ' +
                String(now.getHours()).padStart(2, '0') + ':' +
                String(now.getMinutes()).padStart(2, '0') + ':' +
                String(now.getSeconds()).padStart(2, '0');

            const newSession: ChatSession = {
                id: -Date.now(),
                title,
                created_at: localTimestamp,
                updated_at: localTimestamp
            };
            guestSessions.unshift(newSession);
            this.saveGuestSessions(guestSessions);
            this.currentSessionId.set(newSession.id);
            return of({ session_id: newSession.id });
        }

        return this.http.post<{ session_id: number }>(`${environment.apiUrl}/chats`, { title }, {
            headers: this.getHeaders()
        }).pipe(
            map(res => ({ session_id: res.session_id as number | null })),
            tap(res => {
                if (res.session_id !== null) {
                    this.currentSessionId.set(res.session_id);
                    this.loadSessions().subscribe();
                }
            })
        );
    }

    private saveGuestSessions(sessions: ChatSession[]) {
        // Always sort by updated_at descending before saving
        const sortedSessions = [...sessions].sort((a, b) =>
            new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
        );
        this.sessions.set(sortedSessions);
    }

    getChatDetails(sessionId: number): Observable<any> {
        if (!this.auth.isAuthenticated() || sessionId < 0) {
            const messages: ChatMessage[] = []; // Guest messages are not persisted
            const session = this.sessions().find(s => s.id === sessionId);

            this.currentSessionId.set(sessionId);
            return of({ session: session!, messages });
        }

        return this.http.get<{ session: ChatSession, messages: ChatMessage[] }>(`${environment.apiUrl}/chats/${sessionId}`, {
            headers: this.getHeaders()
        }).pipe(
            tap(() => this.currentSessionId.set(sessionId))
        );
    }

    saveGuestMessage(sessionId: number, message: ChatMessage) {
        if (sessionId >= 0) return; // Only for guest sessions
        // No longer saving to localStorage
        const now = new Date();
        const nowStr = now.getFullYear() + '-' +
            String(now.getMonth() + 1).padStart(2, '0') + '-' +
            String(now.getDate()).padStart(2, '0') + ' ' +
            String(now.getHours()).padStart(2, '0') + ':' +
            String(now.getMinutes()).padStart(2, '0') + ':' +
            String(now.getSeconds()).padStart(2, '0');

        // Message is now only added to internal state via MainSearchComponent threads or in-memory lists if needed
        const messages: ChatMessage[] = []; // In-memory fallback if history needs to be maintained in-session

        messages.push({
            ...message,
            created_at: nowStr
        });

        // Also update the session's updated_at timestamp in the sessions list
        const guestSessions = this.sessions().map(s =>
            s.id === sessionId ? { ...s, updated_at: nowStr } : s
        );
        this.saveGuestSessions(guestSessions);
    }

    renameChat(sessionId: number, title: string): Observable<any> {
        if (!this.auth.isAuthenticated() || sessionId < 0) {
            const now = new Date();
            const nowStr = now.getFullYear() + '-' +
                String(now.getMonth() + 1).padStart(2, '0') + '-' +
                String(now.getDate()).padStart(2, '0') + ' ' +
                String(now.getHours()).padStart(2, '0') + ':' +
                String(now.getMinutes()).padStart(2, '0') + ':' +
                String(now.getSeconds()).padStart(2, '0');

            const guestSessions = this.sessions().map(s =>
                s.id === sessionId ? { ...s, title, updated_at: nowStr } : s
            );
            this.saveGuestSessions(guestSessions);
            return of(null);
        }

        return this.http.put(`${environment.apiUrl}/chats/${sessionId}/rename`, { title }, {
            headers: this.getHeaders()
        }).pipe(
            tap(() => this.loadSessions().subscribe())
        );
    }

    deleteChat(sessionId: number): Observable<any> {
        if (!this.auth.isAuthenticated() || sessionId < 0) {
            const guestSessions = this.sessions().filter(s => s.id !== sessionId);
            this.saveGuestSessions(guestSessions);
            if (this.currentSessionId() === sessionId) {
                this.currentSessionId.set(null);
            }
            return of(null);
        }

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
