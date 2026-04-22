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
  }

  @HostListener('window:mouseup')
  onMouseUp() {
    this.isResizing = false;
  }

  onTextEdit(sectionId: string, event: any) {
    const text = event.target.innerText;
    this.reportService.updateUserOverride(sectionId, text);
  }

  // --- Navigation & UI ---

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

  getDisplayTitle(s: ReportState): string {
    if (!s || !s.sections || !s.sections[0]) return '';
    const formData = s.sections[0].formData || {};
    return formData['project_name'] || formData['campaign_name'] || s.title;
  }

  getRoughNotes(section: SectionState): string {
    if (!section || !section.formData) return '';
    
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
}
