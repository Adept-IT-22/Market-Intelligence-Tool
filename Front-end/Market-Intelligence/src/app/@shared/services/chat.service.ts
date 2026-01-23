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
    private readonly GUEST_SESSIONS_KEY = 'mit_guest_sessions';
    private readonly GUEST_MESSAGES_KEY = 'mit_guest_messages_prefix_';

    sessions = signal<ChatSession[]>([]);
    currentSessionId = signal<number | null>(null);

    constructor(private http: HttpClient, private auth: AuthService) {
        // Restore current session from storage if it exists
        const savedSession = localStorage.getItem(this.SESSION_KEY);
        if (savedSession) {
            this.currentSessionId.set(parseInt(savedSession, 10));
        }

        // Automatically load sessions
        effect(() => {
            if (this.auth.isAuthenticated()) {
                this.loadSessions().subscribe();
            } else {
                this.loadGuestSessions();
            }
        });

        // Persist current session ID when it changes
        effect(() => {
            const id = this.currentSessionId();
            if (id) {
                localStorage.setItem(this.SESSION_KEY, id.toString());
            } else {
                localStorage.removeItem(this.SESSION_KEY);
            }
        });
    }

    private loadGuestSessions() {
        const saved = localStorage.getItem(this.GUEST_SESSIONS_KEY);
        const guestSessions = saved ? JSON.parse(saved) : [];
        this.sessions.set(guestSessions);

        // If current session is a guest session, keep it, otherwise clear
        const currentId = this.currentSessionId();
        if (currentId && !guestSessions.find((s: ChatSession) => s.id === currentId)) {
            // Check if it's a guest ID (usually negative or high random)
            // For now, if it's not in the guest sessions list, clear it
            this.currentSessionId.set(null);
        }
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
        localStorage.setItem(this.GUEST_SESSIONS_KEY, JSON.stringify(sortedSessions));
        this.sessions.set(sortedSessions);
    }

    getChatDetails(sessionId: number): Observable<any> {
        if (!this.auth.isAuthenticated() || sessionId < 0) {
            const saved = localStorage.getItem(this.GUEST_MESSAGES_KEY + sessionId);
            const messages = saved ? JSON.parse(saved) : [];
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

        const saved = localStorage.getItem(this.GUEST_MESSAGES_KEY + sessionId);
        const messages = saved ? JSON.parse(saved) : [];

        const now = new Date();
        const nowStr = now.getFullYear() + '-' +
            String(now.getMonth() + 1).padStart(2, '0') + '-' +
            String(now.getDate()).padStart(2, '0') + ' ' +
            String(now.getHours()).padStart(2, '0') + ':' +
            String(now.getMinutes()).padStart(2, '0') + ':' +
            String(now.getSeconds()).padStart(2, '0');

        messages.push({
            ...message,
            created_at: nowStr
        });
        localStorage.setItem(this.GUEST_MESSAGES_KEY + sessionId, JSON.stringify(messages));

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
            localStorage.removeItem(this.GUEST_MESSAGES_KEY + sessionId);
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
