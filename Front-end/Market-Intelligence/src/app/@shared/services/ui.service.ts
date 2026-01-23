import { Injectable, signal } from '@angular/core';

@Injectable({
    providedIn: 'root'
})
export class UiService {
    private readonly SIDEBAR_STATE_KEY = 'mit_sidebar_expanded';

    isSidebarExpanded = signal<boolean>(this.getInitialSidebarState());

    constructor() { }

    private getInitialSidebarState(): boolean {
        const saved = localStorage.getItem(this.SIDEBAR_STATE_KEY);
        return saved !== null ? saved === 'true' : true;
    }

    toggleSidebar() {
        const newState = !this.isSidebarExpanded();
        this.isSidebarExpanded.set(newState);
        localStorage.setItem(this.SIDEBAR_STATE_KEY, newState.toString());
    }
}
