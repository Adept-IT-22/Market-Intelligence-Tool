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
  aiDraft?: string;
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
    risks: { text: string; target_id: string }[];
    inconsistencies: { text: string; target_id: string }[];
    suggestions: { text: string; target_id: string }[];
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
   * Calls AI to parse unstructured notes into structured form data.
   */
  autoFillFromNotes(type: string, raw_text: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/auto-fill`, { type, raw_text }).pipe(
      tap((res: any) => {
        if (res.success && this.stateSubject.value) {
          const currentState = this.stateSubject.value;
          const extracted = res.answers || {};
          
          const updatedSections = currentState.sections.map(s => {
            const newFormData = { ...s.formData };
            Object.keys(extracted).forEach(k => {
              let val = extracted[k];
              // Only overwrite if the AI actually extracted something meaningful
              if (val !== undefined && val !== null && val !== "") {
                // Safeguard: If AI returns an object instead of a string, flatten it
                if (typeof val === 'object' && val !== null) {
                  val = val.answer || val.value || val.name || val.text || val.content || JSON.stringify(val);
                }
                newFormData[k] = val;
              }
            });
            return { ...s, formData: newFormData };
          });
          
          this.stateSubject.next({ ...currentState, sections: updatedSections });
        }
      })
    );
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
        const latestState = this.stateSubject.value;
        if (res.success && latestState && res.draft) {
          // res.draft is the metadata object which contains a 'sections' array
          const incomingSections = res.draft.sections || [];
          const sectionsMap = new Map<string, any>(incomingSections.map((s: any) => [s.id, s]));

          const updatedSections = latestState.sections.map(s => {
            const draftData = sectionsMap.get(s.id);
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
          this.stateSubject.next({ ...latestState, sections: updatedSections, isGenerating: false });
          this.analyzeReport(); // Trigger analysis ONLY after generation
        }
      }),
      finalize(() => {
        const latestState = this.stateSubject.value;
        if (latestState) {
          this.stateSubject.next({ ...latestState, isGenerating: false });
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
        const latestState = this.stateSubject.value;
        if (res.success && latestState) {
          const finalSections = latestState.sections.map(s => {
            if (s.id === sectionId) {
              return { ...s, aiDraft: res.refined_text, userOverride: null, isEdited: false, isThinking: false };
            }
            return s;
          });
          this.stateSubject.next({ ...latestState, sections: finalSections });
          this.analyzeReport();  // Trigger analysis after refinement
        }
      }),
      finalize(() => {
        const latestState = this.stateSubject.value;
        if (!latestState) return;
        const resetSections = latestState.sections.map(s =>
          s.id === sectionId ? { ...s, isThinking: false } : s
        );
        this.stateSubject.next({ ...latestState, sections: resetSections });
      })
    );
  }

  /**
   * The 'Advisor' Layer.
   */
  private analysisTimeout: any;
  analyzeReport() {
    const state = this.stateSubject.value;
    if (!state) return;

    // Debounce analysis to avoid spamming the backend during typing
    if (this.analysisTimeout) clearTimeout(this.analysisTimeout);
    
    this.analysisTimeout = setTimeout(() => {
      // Build the plain text object for analysis
      const sectionsObj: any = {};
      state.sections.forEach(s => {
        // Use userOverride -> aiDraft -> formData fallback (simple summary of keys)
        let content = s.userOverride ?? s.aiDraft ?? '';
        if (!content.trim() && s.formData && s.id !== 'metadata') {
          content = Object.entries(s.formData)
            .filter(([_, v]) => v)
            .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
            .join('\n');
        }
        sectionsObj[s.id] = content;
      });

      this.http.post(`${this.apiUrl}/analyze`, { type: state.type, sections: sectionsObj }).subscribe((res: any) => {
        if (res.success) {
          this.stateSubject.next({ ...state, analysis: res.analysis });
        }
      });
    }, 1000); // 1 second debounce
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
    }
  }

  updateSectionForm(sectionId: string, field: string, value: any) {
    const state = this.stateSubject.value;
    if (state) {
      const updatedSections = state.sections.map(s => {
        if (s.id === sectionId) {
          return {
            ...s,
            formData: {
              ...s.formData,
              [field]: value
            }
          };
        }
        return s;
      });
      this.stateSubject.next({ ...state, sections: updatedSections });
    }
  }

  updateSectionDraft(sectionId: string, draft: string) {
    const state = this.stateSubject.value;
    if (state) {
      const updatedSections = state.sections.map(s => {
        if (s.id === sectionId) {
          return {
            ...s,
            aiDraft: draft,
            confidence: { level: 'High' as 'High' | 'Med' | 'Low', reason: 'Verified demo data' }
          };
        }
        return s;
      });
      this.stateSubject.next({ ...state, sections: updatedSections });
    }
  }

  exportReport() {
    const state = this.stateSubject.value;
    if (!state) return null;

    // Send full sections list so the template has access to both Synthesis and raw Form Data
    return this.http.post(`${this.apiUrl}/export`, { 
      type: state.type, 
      sections: state.sections,
      title: state.title
    }, { responseType: 'blob' });
  }
  
  exportReportMd() {
    const state = this.stateSubject.value;
    if (!state) return null;

    return this.http.post(`${this.apiUrl}/export-md`, { 
      type: state.type, 
      sections: state.sections,
      title: state.title
    }, { responseType: 'blob' });
  }
}
