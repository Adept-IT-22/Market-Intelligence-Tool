import { Injectable, signal, PLATFORM_ID, Inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

@Injectable({
    providedIn: 'root'
})
export class UiService {
    private readonly SIDEBAR_STATE_KEY = 'mit_sidebar_expanded';

    isSidebarExpanded = signal<boolean>(true);

    constructor(@Inject(PLATFORM_ID) private platformId: Object) {
        if (isPlatformBrowser(this.platformId)) {
            this.isSidebarExpanded.set(this.getInitialSidebarState());
        }
    }

    private getInitialSidebarState(): boolean {
        if (!isPlatformBrowser(this.platformId)) return true;
        const saved = localStorage.getItem(this.SIDEBAR_STATE_KEY);
        return saved !== null ? saved === 'true' : true;
    }

    toggleSidebar() {
        const newState = !this.isSidebarExpanded();
        this.isSidebarExpanded.set(newState);
        if (isPlatformBrowser(this.platformId)) {
            localStorage.setItem(this.SIDEBAR_STATE_KEY, newState.toString());
        }
    }
}
