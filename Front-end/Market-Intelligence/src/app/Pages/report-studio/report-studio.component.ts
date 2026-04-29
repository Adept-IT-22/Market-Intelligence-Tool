import { Component, OnInit, inject, signal, HostListener, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDividerModule } from '@angular/material/divider';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { ReportService, ReportState, SectionState } from '../../@shared/services/report.service';
import { BaseLayoutComponent } from '../../@shared/components/base-layout/base-layout.component';
import { MarkdownModule } from 'ngx-markdown';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-report-studio',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MatIconModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatMenuModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    MatDividerModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MarkdownModule,
    BaseLayoutComponent
  ],
  templateUrl: './report-studio.component.html',
  styleUrls: ['./report-studio.component.scss']
})
export class ReportStudioComponent implements OnInit {
  public reportService = inject(ReportService);
  
  public state = signal<ReportState | null>(null);
  public sectionSchema = signal<any[]>([]);  // Auto-Fill State
  showAutoFill = signal<boolean>(false);
  autoFillText = signal<string>('');
  isAutoFilling = signal<boolean>(false);

  // Resizing Advisor Shelf
  public advisorHeight = signal(220);
  private isResizing = false;
  private startY = 0;
  private startHeight = 0;

  // Computed state derivations/labels
  public activeSectionIndex = signal(0);
  public initError = signal<string | null>(null);
  public showPreview = signal(false);
  
  @ViewChild('previewOverlay', { static: false }) previewOverlay!: ElementRef;
  private stateSub?: Subscription;
  
  // Branding Configuration
  public brandLogo = '/adept_logo.jpg';
  public brandLogoUi = '/transparent adept logo.png';
  public brandSidebar = '/adept_sidebar.png';
  public brandFooter = '/adept_footer.png';
  
  public get currentMonthYear(): string {
    const s = this.state();
    if (s && s.sections && s.sections[0]) {
      const fd = s.sections[0].formData || {};
      const dateVal = fd['period'] || fd['week_of'] || fd['report_date'];
      if (dateVal) {
        const d = new Date(dateVal);
        if (!isNaN(d.getTime())) {
          return d.toLocaleDateString('en-US', { day: 'numeric', month: 'long', year: 'numeric' }).toUpperCase();
        }
      }
    }
    return new Date().toLocaleDateString('en-US', { day: 'numeric', month: 'long', year: 'numeric' }).toUpperCase();
  }
  public projectTitle = 'Strategic Market Intelligence';

  public reportTypes = [
    { id: 'sprint', name: 'Sprint Report' },
    { id: 'marketing', name: 'Marketing Report' },
    { id: 'weekly', name: 'Weekly Report' },
    { id: 'monthly', name: 'Monthly Report' }
  ];

  public selectedType = signal('sprint');

  ngOnInit() {
    this.loadSchema('sprint');
    this.stateSub = this.reportService.state$.subscribe(s => this.state.set(s));
  }
  
  ngOnDestroy() {
    if (this.stateSub) {
      this.stateSub.unsubscribe();
    }
  }

  loadDemoData() {
    const s = this.state();
    if (!s) return;

    // 1. Metadata
    this.onFormChange('metadata', 'project_name', 'Manuh Market Intelligence Platform');
    this.onFormChange('metadata', 'report_by', 'Emmanuel Mwendia Maina');
    this.onFormChange('metadata', 'sprint_no', 4);
    this.onFormChange('metadata', 'period', new Date('2026-04-22'));
    this.onFormChange('metadata', 'sprint_goal', 'Deliver a functional Market Intelligence MVP module with:\n- Completed frontend dashboard views\n- Integrated report generation (Report Studio)\n- Initial data pipeline validation');
    this.onFormChange('metadata', 'sprint_scope', 'This sprint focused on transitioning Manuh from UI completion → functional analytics system.\n\nIncluded:\n- Dashboard UI finalization\n- Report Studio implementation\n- Basic data flow integration (mock/live hybrid)\n\nExcluded:\n- Advanced analytics models\n- Full production deployment\n- External API integrations');

    // 2. Intro
    this.onFormChange('intro', 'executive_summary', 'Core system components were successfully built and integrated. However, deployment and full system validation remain incomplete, pushing critical tasks into the next sprint.');

    // 3. Status
    this.onFormChange('status', 'status_rating', 'Delayed');
    this.onFormChange('status', 'summary_text', 'Core system components were successfully built and integrated. However, deployment and full system validation remain incomplete, pushing critical tasks into the next sprint.');
    this.onFormChange('status', 'timeline', 'April 8 – April 22, 2026');
    this.onFormChange('status', 'time_spent', '167 hours');

    // 4. Progress
    this.onFormChange('progress_detail', 'tasks_completed', '✅ Analytics Dashboard (UI + partial data binding)\n✅ Report Studio (create, preview, export reports)\n✅ Frontend–Backend communication (core endpoints working)');

    // 5. Next Sprint
    this.onFormChange('next_sprint', 'future_tasks', '⏳ Server deployment\n- Advanced analytics models\n- External API integrations');

    // 6. Issues
    this.onFormChange('issues', 'issue_list', 'Deployment and full system validation remain incomplete, pushing critical tasks into the next sprint.\nMissing production SSL certificates.\nPending third-party security audit.');

    // 7. Approvals
    this.onFormChange('next_steps', 'pending_approvals', 'Server deployment authorization\nFinal usability validation approval\nProduction environment access');
    
    this.reportService.updateSectionDraft('intro', '#### Executive Summary\nCore system components were successfully built and integrated. However, deployment and full system validation remain incomplete, pushing critical tasks into the next sprint. The team is focusing on stabilization and environment readiness.');

    this.reportService.updateSectionDraft('status', '#### Overall Status Summary\nWe are currently in a **Delayed** state due to environment provisioning bottlenecks. While technical development is 90% complete, the integration validation phase requires a stable production-like environment which is pending approval.');

    this.reportService.updateSectionDraft('next_steps', '#### Required Approvals\n- **Production Environment:** Critical sign-off needed by end of week.\n- **Security Audit:** Initial findings require remediation before live deployment.\n- **User Acceptance:** Scheduled for the first week of May.');

    this.reportService.updateSectionDraft('progress_detail', '#### Key Accomplishments\n- **Analytics Dashboard:** Completed all UI components and partial data binding.\n- **Report Studio:** End-to-end workflow implemented (create, preview, export).\n- **API Integration:** Core frontend-backend communication endpoints are operational.');
    
    this.reportService.updateSectionDraft('next_sprint', '#### Upcoming Priorities\n- **Server Deployment:** Critical task pushed to next sprint.\n- **Advanced Models:** Integration of predictive analytics.\n- **External APIs:** Finalizing third-party data connectors.');
    
    this.reportService.updateSectionDraft('qa', '#### QA Metrics & Findings\n- **Test Coverage:** 84% unit test coverage achieved.\n- **Bugs Identified:** 12 minor UI glitches found (fixed).\n- **Performance:** Average response time < 200ms for core dashboards.');
    
    this.reportService.updateSectionDraft('issues', '#### Current Blockers\n- **Deployment:** Awaiting production environment provisioning.\n- **Validation:** Full end-to-end system testing delayed by 2 days.');
  }

  loadSchema(type: string) {
    this.selectedType.set(type);
    this.reportService.getReportSchema(type).subscribe({
      next: (res) => {
        const title = this.reportTypes.find(t => t.id === type)?.name || 'New Report';
        this.sectionSchema.set(res.schema); // Store schema
        this.reportService.initReport(type, title, res.schema);
        this.initError.set(null);
      },
      error: (err) => {
        console.error('Failed to initialize Studio:', err);
        this.initError.set('Could not connect to the Adept Report Engine. Please ensure the backend is running.');
      }
    });
  }

  // --- Actions ---

  onFormChange(sectionId: string, field: string, value: any) {
    const s = this.state();
    if (!s) return;
    
    const updatedSections = s.sections.map(sec => {
      if (sec.id === sectionId) {
        return {
          ...sec,
          formData: {
            ...sec.formData,
            [field]: value
          }
        };
      }
      return sec;
    });

    // We can directly update the BehaviorSubject via a new method inside reportService if we wanted fully robust abstraction, 
    // but since state is public/readonly theoretically, we manually update the service's stateSubject via an internal method or just re-initing.
    // For now we'll trigger a full state update. Actually, `reportService` doesn't expose a method to arbitrarily update state, so we update the local signal, but to fix the desync we must update the service state properly.
    // However, looking at report.service.ts we added `updateUserOverride`, maybe we need `updateSectionForm`.
    // Wait, let's fix it by adding another method in ReportService. I will just do a hacky workaround if not available, wait, let me just add it to ReportService instead inside another tool call. I'll just temporarily update the formData then I'll use ReportService when I edit it next.
    // Or we can just use the provided ReportService instance and access `stateSubject`. Wait, `stateSubject` is private.
    // Let's implement an emitted event. I'll update ReportService.ts right after this.
    this.reportService.updateSectionForm(sectionId, field, value);
  }

  generateReport() {
    const s = this.state();
    if (!s) return;

    // Build flat answers object from all sections
    const answers: any = {};
    s.sections.forEach(sec => {
      Object.assign(answers, sec.formData);
    });

    this.reportService.generateReport(s.type, answers).subscribe();
  }

  triggerAutoFill() {
    const text = this.autoFillText();
    const s = this.state();
    if (!text.trim() || !s) return;

    this.isAutoFilling.set(true);
    this.reportService.autoFillFromNotes(s.type, text).subscribe({
      next: () => {
        this.isAutoFilling.set(false);
        this.showAutoFill.set(false);
        this.autoFillText.set('');
      },
      error: (err) => {
        this.isAutoFilling.set(false);
        console.error('AutoFill failed', err);
      }
    });
  }

  refine(sectionId: string, action: string) {
    this.reportService.refineSection(sectionId, action)?.subscribe();
  }

  // --- Resizing Logic for Advisor Shelf ---
  startResizing(event: MouseEvent) {
    this.isResizing = true;
    this.startY = event.clientY;
    this.startHeight = this.advisorHeight();
    event.preventDefault();
  }

  @HostListener('window:mousemove', ['$event'])
  onMouseMove(event: MouseEvent) {
    if (!this.isResizing) return;
    const deltaY = this.startY - event.clientY;
    const newHeight = Math.min(Math.max(this.startHeight + deltaY, 120), 600);
    this.advisorHeight.set(newHeight);
    
    // Prevent selection while resizing
    document.body.classList.add('resizing-active');
  }

  @HostListener('window:mouseup')
  onMouseUp() {
    this.isResizing = false;
    document.body.classList.remove('resizing-active');
  }

  onTextEdit(sectionId: string, event: any) {
    const text = event.target.innerText;
    this.reportService.updateUserOverride(sectionId, text);
  }

  /**
   * Automatically fixes numbering in the draft text (e.g. 1.1 -> 2.1)
   * to ensure section sub-headers match the actual section index.
   */
  fixNumbering(text: string | undefined, sectionIndex: any): string {
    if (!text) return '';
    // If sectionIndex is a string (like from getTOCIndex), convert to int or use as prefix
    const prefix = sectionIndex;
    
    // Replace any line starting with "X.Y" or "X.Y.Z" etc.
    // Captures the leading bolding/spacing, the first digit (to be replaced), 
    // and then all subsequent dots and digits.
    const regex = /^(\s*(\*\*|))(\d+)(\.[\d\.]+)/gm;
    return text.replace(regex, `$1${prefix}$4`);
  }

  // --- Navigation & UI ---

  getTOCIndex(sections: any[], currentIndex: number): string {
    const currentSection = sections[currentIndex];
    if (currentSection.id === 'metadata' || currentSection.id === 'toc') return '';
    
    return `${currentIndex}`;
  }

  getTOCPage(sections: any[], currentIndex: number): number {
    // Index 0 (Metadata) is on Cover -> P1
    if (currentIndex === 0) return 1;

    // Index 1 (Introduction) starts on P3
    if (currentIndex === 1) return 3;

    // Subsequent sections start from P4 onwards
    let page = 2 + currentIndex;
    
    // Account for potential Intro splitting (shifts all pages after Index 1)
    if (this.shouldSplitIntro(this.state()) && currentIndex > 1) {
      page += 1;
    }

    // Account for potential Issues & Blockers splitting (Section 5 -> Index 6 usually? No, check indices)
    // Actually, let's use the actual index. 
    // Metadata=0, Intro=1, Status=2, Progress=3, NextSprint=4, QA=5, Issues=6, Approvals=7
    if (this.shouldBreakIssues(this.state()) && currentIndex > 6) {
      page += 1;
    }

    return page;
  }

  hasVisibleSectionAfter(sections: any[], currentIndex: number): boolean {
    for (let i = currentIndex + 1; i < sections.length; i++) {
      if (sections[i].id !== 'metadata' && sections[i].id !== 'status') {
        return true;
      }
    }
    return false;
  }

  scrollToTop() {
    const el = document.querySelector('.document-scroller');
    if (el) {
      el.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  scrollToSection(index: number) {
    this.activeSectionIndex.set(index);
    const section = this.state()?.sections[index];
    if (section) {
      const el = document.getElementById(`render-${section.id}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  }

  nextSection() {
    const nextIndex = this.activeSectionIndex() + 1;
    if (nextIndex < (this.state()?.sections.length || 0)) {
      this.scrollToSection(nextIndex);
    }
  }

  openPreview() {
    this.showPreview.set(true);
    document.body.style.overflow = 'hidden';
    setTimeout(() => {
      if (this.previewOverlay) {
        this.previewOverlay.nativeElement.focus();
      }
    }, 0);
  }

  closePreview() {
    this.showPreview.set(false);
    document.body.style.overflow = '';
  }

  exportReport() {
    const obs = this.reportService.exportReport();
    if (!obs) return;

    obs.subscribe({
      next: (blob: Blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Report_${this.selectedType()}_${new Date().toISOString().split('T')[0]}.docx`;
        a.click();
        window.URL.revokeObjectURL(url);
      },
      error: (err) => {
        console.error('Export failed:', err);
      }
    });
  }

  exportReportMd() {
    const obs = this.reportService.exportReportMd();
    if (!obs) return;

    obs.subscribe({
      next: (blob: Blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Report_${this.selectedType()}_${new Date().toISOString().split('T')[0]}.md`;
        a.click();
        window.URL.revokeObjectURL(url);
      },
      error: (err) => {
        console.error('Markdown export failed:', err);
      }
    });
  }

  setActiveSection(index: number) {
    this.activeSectionIndex.set(index);
    const s = this.state();
    if (s && s.sections[index]) {
      // Allow DOM to update if needed, then scroll
      setTimeout(() => {
        const element = document.getElementById('render-' + s.sections[index].id);
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }, 0);
    }
  }

  getDisplayTitle(s: ReportState | null): string {
    if (!s || !s.sections || !s.sections[0]) return '';
    const formData = s.sections[0].formData || {};
    let title = formData['project_name'] || formData['campaign_name'] || s.title || '';
    
    // If title is an object, extract a string property
    if (typeof title === 'object' && title !== null) {
      title = (title as any).value || (title as any).name || (title as any).text || (title as any).content || 'New Report';
    }
    
    return String(title);
  }

  getMetadata(s: ReportState | null) {
    if (!s || !s.sections || !s.sections[0]) return null;
    const formData = s.sections[0].formData || {};
    return {
      project: formData['project_name'] || 'Market Intelligence',
      preparedBy: formData['prepared_by'] || 'Adept Studio',
      date: formData['reporting_date'] || this.currentMonthYear,
      type: this.reportTypes.find(t => t.id === s.type)?.name || 'Strategic Report'
    };
  }

  getRoughNotes(section: any): string {
    if (!section || !section.formData || section.id === 'metadata') return '';
    
    // Convert the formData object into an array of strings, properly stringifying arrays (like bullet points) or objects, and filtering out empty values.
    const values = Object.entries(section.formData).map(([k, v]) => {
      // Exclude simple internal statuses like Dropdowns if they aren't the main content, 
      // but easiest is just to combine all textual answers so the user sees *something* live.
      if (!v) return null;
      if (typeof v === 'string' && v.trim().length === 0) return null;
      if (Array.isArray(v)) return v.join('\n');
      return String(v);
    }).filter(v => v !== null) as string[];

    return values.join('\n\n');
  }

  /**
   * Returns the best available content for a section following the truth hierarchy:
   * userOverride → aiDraft → formatted formData → empty string
   */
  getSectionContent(section: any): string {
    if (!section) return '';
    
    // Priority 1 & 2: AI-generated or user-edited content
    const synthesized = section.userOverride ?? section.aiDraft;
    if (synthesized && synthesized.trim()) return synthesized;
    
    // Priority 3: Fall back to raw form data, formatted as markdown
    if (section.formData && section.id !== 'metadata') {
      const lines: string[] = [];
      for (const [key, value] of Object.entries(section.formData)) {
        if (!value) continue;
        const val = String(value).trim();
        if (!val) continue;
        const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        if (val.includes('\n')) {
          lines.push(`**${label}:**`);
          val.split('\n').filter((l: string) => l.trim()).forEach((l: string) => {
            const trimmed = l.trim();
            if (trimmed.match(/^[-*•✅⏳]/)) {
              lines.push(trimmed);
            } else {
              lines.push(`- ${trimmed}`);
            }
          });
        } else {
          lines.push(`**${label}:** ${val}`);
        }
      }
      return lines.join('\n');
    }
    
    return '';
  }

  hasSectionContent(section: any): boolean {
    return !!this.getSectionContent(section).trim();
  }

  getAggregatedWhatNext(s: ReportState | null): string[] {
    if (!s || !s.sections) return [];
    
    const nextSprint = s.sections.find(sec => sec.id === 'next_sprint');
    const approvals = s.sections.find(sec => sec.id === 'next_steps');
    
    let combined: string[] = [];
    
    const cleanItem = (item: string) => {
      // Remove leading bullets, various dashes (en, em), numbers, and spaces
      // Handling -, *, •, ., –, —, and digit-based lists
      return item.replace(/^[•\-\*\. \d–—]+\s*/, '').trim();
    };
    
    if (nextSprint?.formData?.['future_tasks']) {
      const tasks = String(nextSprint.formData['future_tasks'])
        .split('\n')
        .filter(t => t.trim())
        .map(cleanItem);
      combined = [...combined, ...tasks];
    }
    
    if (approvals?.formData?.['pending_approvals']) {
      const apps = String(approvals.formData['pending_approvals'])
        .split('\n')
        .filter(t => t.trim())
        .map(cleanItem);
      
      if (combined.length > 0 && apps.length > 0) {
        combined.push('**Required Approvals:**');
      }
      combined = [...combined, ...apps];
    }
    
    return combined.slice(0, 5); 
  }

  getSummaryHighlights(s: ReportState | null): string[] {
    if (!s || !s.sections) return [];
    const progress = s.sections.find(sec => sec.id === 'progress_detail');
    if (!progress?.formData?.['tasks_completed']) return [];
    
    return String(progress.formData['tasks_completed'])
      .split('\n')
      .filter(t => t.trim())
      .map(t => t.replace(/^[•\-\*\. \d–—✅]+\s*/, '').trim())
      .slice(0, 4);
  }

  getSplitIntro(s: ReportState | null, part: 1 | 2): string {
    if (!s || !s.sections || !s.sections[1]) return '';
    const text = s.sections[1].userOverride ?? s.sections[1].aiDraft ?? '';
    
    // Heuristic: ~2500 chars fit Page 3 (with the summary boxes)
    const splitPoint = 2200; 
    
    if (text.length <= splitPoint) {
      return part === 1 ? text : '';
    }
    
    // Find a good paragraph break near the split point
    let breakIndex = text.lastIndexOf('\n', splitPoint);
    if (breakIndex < splitPoint / 2) breakIndex = splitPoint; // Fallback

    if (part === 1) {
      return text.substring(0, breakIndex);
    } else {
      return text.substring(breakIndex).trim();
    }
  }

  shouldSplitIntro(s: ReportState | null): boolean {
    if (!s || !s.sections || !s.sections[1]) return false;
    const text = s.sections[1].userOverride ?? s.sections[1].aiDraft ?? '';
    return text.length > 2200;
  }

  shouldBreakOverallStatus(s: ReportState | null): boolean {
    if (!s || !s.sections) return false;
    
    // Always break if the Intro is already splitting onto two pages
    if (this.shouldSplitIntro(s)) return true;

    // Check the Intro content length (both form data and AI draft)
    const introLen = Math.max(
      (s.sections[1]?.formData?.['executive_summary'] || '').length,
      (s.sections[1]?.userOverride ?? s.sections[1]?.aiDraft ?? '').length
    );

    // Check the Status content length
    const statusLen = Math.max(
      (s.sections[2]?.formData?.['summary_text'] || '').length,
      (s.sections[2]?.userOverride ?? s.sections[2]?.aiDraft ?? '').length
    );
    
    // If combined visible content is substantial, break to new page
    return (introLen + statusLen) > 300; // Increased threshold for AI drafts
  }

  shouldBreakIssues(s: ReportState | null): boolean {
    if (!s || !s.sections || !s.sections[6]) return false;
    const section = s.sections[6];
    const text = section.userOverride ?? section.aiDraft ?? '';
    // Only break if content is long AND contains the split marker
    return text.length > 1400 && text.includes('Next Steps'); 
  }

  getSplitIssues(s: ReportState | null, part: 1 | 2): string {
    if (!s || !s.sections || !s.sections[6]) return '';
    const text = s.sections[6].userOverride ?? s.sections[6].aiDraft ?? '';
    
    // Find the "Next Steps" or similar header to split at
    const splitTerm = 'Next Steps';
    const splitIndex = text.indexOf(splitTerm);
    
    if (splitIndex === -1 || text.length < 1200) {
      return part === 1 ? text : '';
    }

    if (part === 1) {
      return text.substring(0, splitIndex).trim();
    } else {
      return text.substring(splitIndex).trim();
    }
  }

  runAdvisor() {
    this.reportService.analyzeReport();
  }

  jumpToFix(targetId: string) {
    const s = this.state();
    if (!s) return;
    
    const index = s.sections.findIndex(sec => sec.id === targetId);
    if (index >= 0) {
      this.setActiveSection(index);
      
      // Add a temporary highlight to the form field
      setTimeout(() => {
        const field = document.getElementById(`field-${targetId}`);
        if (field) {
          field.classList.add('highlight-guide');
          setTimeout(() => field.classList.remove('highlight-guide'), 3000);
        }
      }, 500);
    }
  }
}
