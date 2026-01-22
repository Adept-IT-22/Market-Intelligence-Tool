import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '@environments/environment';
import { tap, catchError, of, map } from 'rxjs';

export interface User {
  id: number;
  email: string;
  displayName?: string;
}

interface AuthResponse {
  token: string;
  user: User;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private readonly TOKEN_KEY = 'mit_auth_token';
  
  // Use signals for reactive state
  currentUser = signal<User | null>(null);
  isAuthenticated = signal<boolean>(false);

  constructor(private http: HttpClient) {
    this.loadUserFromStorage();
  }

  private loadUserFromStorage() {
    const token = localStorage.getItem(this.TOKEN_KEY);
    if (token) {
      // We have a token, but we should probably verify it or at least load it
      // For now, we'll try to get user info. If it fails, token is invalid.
      this.getMe().subscribe();
    }
  }

  signup(email: string, password: string, displayName?: string) {
    return this.http.post<AuthResponse>(`${environment.apiUrl}/auth/signup`, {
      email, password, displayName
    }).pipe(
      tap(res => this.handleAuthSuccess(res))
    );
  }

  login(email: string, password: string) {
    return this.http.post<AuthResponse>(`${environment.apiUrl}/auth/login`, {
      email, password
    }).pipe(
      tap(res => this.handleAuthSuccess(res))
    );
  }

  logout() {
    localStorage.removeItem(this.TOKEN_KEY);
    this.currentUser.set(null);
    this.isAuthenticated.set(false);
  }

  getMe() {
    return this.http.get<{user: User}>(`${environment.apiUrl}/auth/me`, {
      headers: { 'Authorization': `Bearer ${this.getToken()}` }
    }).pipe(
      tap(res => {
        this.currentUser.set(res.user);
        this.isAuthenticated.set(true);
      }),
      catchError(err => {
        this.logout();
        return of(null);
      })
    );
  }

  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  private handleAuthSuccess(res: AuthResponse) {
    localStorage.setItem(this.TOKEN_KEY, res.token);
    this.currentUser.set(res.user);
    this.isAuthenticated.set(true);
  }
}
