import { Injectable, signal, computed, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap, finalize } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface Confidence {
  level: 'High' | 'Med' | 'Low';
  reason: string;
}

export interface SectionState {
  id: string;
  title: string;
  formData: any;
  aiDraft: string;
  userOverride?: string | null;
  isEdited: boolean;
  confidence: Confidence;
  isThinking: boolean;
}

export interface ReportState {
  type: string;
  title: string;
  sections: SectionState[];
  analysis?: {
    risks: string[];
    inconsistencies: string[];
    suggestions: string[];
  };
  isGenerating: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class ReportService {
  private http = inject(HttpClient);
  private apiUrl = `${environment.apiUrl}/reports`;

  // --- RxJS State Management ---
  private stateSubject = new BehaviorSubject<ReportState | null>(null);
  public state$ = this.stateSubject.asObservable();

  constructor() {}

  // --- Discovery ---
  getReportTypes(): Observable<any> {
    return this.http.get(`${this.apiUrl}/types`);
  }

  getReportSchema(type: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/questions/${type}`);
  }

  // --- Core Lifecycle ---
  
  /**
   * Initializes a new report state based on the schema.
   */
  initReport(type: string, title: string, schema: any[]) {
    const initialState: ReportState = {
      type,
      title,
      sections: schema.map(s => ({
        id: s.id,
        title: s.title,
        formData: {},
        aiDraft: '',
        userOverride: null,
        isEdited: false,
        confidence: { level: 'Low', reason: 'Waiting for data...' },
        isThinking: false
      })),
      isGenerating: false
    };
    this.stateSubject.next(initialState);
  }

  /**
   * Triggers full report generation.
   */
  generateReport(type: string, answers: any) {
    const currentState = this.stateSubject.value;
    if (currentState) {
      this.stateSubject.next({ ...currentState, isGenerating: true });
    }

    return this.http.post(`${this.apiUrl}/generate`, { type, answers }).pipe(
      tap((res: any) => {
        if (res.success && currentState) {
          const updatedSections = currentState.sections.map(s => {
            const draftData = res.draft[s.id];
            if (draftData) {
              return {
                ...s,
                aiDraft: draftData.aiDraft,
                confidence: draftData.confidence,
                isEdited: false, // Reset edit flag on full regen
                userOverride: null // Clear overrides on full regen
              };
            }
            return s;
          });
          this.stateSubject.next({ ...currentState, sections: updatedSections, isGenerating: false });
          this.analyzeReport(); // Trigger analysis automatically
        }
      }),
      finalize(() => {
        if (this.stateSubject.value) {
          this.stateSubject.next({ ...this.stateSubject.value, isGenerating: false });
        }
      })
    );
  }

  /**
   * specialized Section Refinement (The Co-pilot).
   */
  refineSection(sectionId: string, action: string) {
    const state = this.stateSubject.value;
    if (!state) return null;

    const section = state.sections.find(s => s.id === sectionId);
    if (!section) return null;

    // Set thinking state
    const thinkingSections = state.sections.map(s => s.id === sectionId ? { ...s, isThinking: true } : s);
    this.stateSubject.next({ ...state, sections: thinkingSections });

    const payload = {
      type: state.type,
      section_id: sectionId,
      action: action,
      current_text: section.userOverride ?? section.aiDraft,
      answers: section.formData
    };

    return this.http.post(`${this.apiUrl}/refine`, payload).pipe(
      tap((res: any) => {
        if (res.success) {
          const finalSections = state.sections.map(s => {
            if (s.id === sectionId) {
              return { ...s, aiDraft: res.refined_text, userOverride: null, isEdited: false, isThinking: false };
            }
            return s;
          });
          this.stateSubject.next({ ...state, sections: finalSections });
        }
      }),
      finalize(() => {
        const resetSections = this.stateSubject.value?.sections.map(s => ({ ...s, isThinking: false })) || [];
        this.stateSubject.next({ ...this.stateSubject.value!, sections: resetSections });
      })
    );
  }

  /**
   * The 'Advisor' Layer.
   */
  analyzeReport() {
    const state = this.stateSubject.value;
    if (!state) return;

    // Build the plain text object for analysis
    const sectionsObj: any = {};
    state.sections.forEach(s => {
      sectionsObj[s.id] = s.userOverride ?? s.aiDraft;
    });

    this.http.post(`${this.apiUrl}/analyze`, { type: state.type, sections: sectionsObj }).subscribe((res: any) => {
      if (res.success) {
        this.stateSubject.next({ ...state, analysis: res.analysis });
      }
    });
  }

  /**
   * Truth Hierarchy Edits.
   */
  updateUserOverride(sectionId: string, text: string) {
    const state = this.stateSubject.value;
    if (state) {
      const updatedSections = state.sections.map(s => {
        if (s.id === sectionId) {
          return { ...s, userOverride: text, isEdited: true };
        }
        return s;
      });
      this.stateSubject.next({ ...state, sections: updatedSections });
      // Debounced auto-save could go here
    }
  }

  exportReport() {
    const state = this.stateSubject.value;
    if (!state) return null;

    const data: any = {};
    state.sections.forEach(s => {
      data[s.id] = s.userOverride ?? s.aiDraft;
    });

    return this.http.post(`${this.apiUrl}/export`, { type: state.type, data: data }, { responseType: 'blob' });
  }
}
