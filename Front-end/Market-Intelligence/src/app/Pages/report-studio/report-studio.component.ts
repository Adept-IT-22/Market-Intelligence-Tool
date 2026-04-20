import { Component, OnInit, inject, signal } from '@angular/core';
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
import { ReportService, ReportState, SectionState } from '../../@shared/services/report.service';
import { BaseLayoutComponent } from '../../@shared/components/base-layout/base-layout.component';

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
    MatTooltipModule,
    MatDividerModule,
    BaseLayoutComponent
  ],
  templateUrl: './report-studio.component.html',
  styleUrls: ['./report-studio.component.scss']
})
export class ReportStudioComponent implements OnInit {
  public reportService = inject(ReportService);
  
  public state = signal<ReportState | null>(null);
  public sectionSchema = signal<any[]>([]); // Added to store questions/labels
  public activeSectionIndex = signal(0);
  public initError = signal<string | null>(null);
  
  // Branding Configuration
  public brandLogo = '/adept_logo.jpg';
  public brandSidebar = '/adept_sidebar.png';
  public brandFooter = '/adept_footer.png';
  
  public currentDate = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
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
    this.reportService.state$.subscribe(s => this.state.set(s));
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
    
    // Update local form state for the specific section
    const section = s.sections.find(sec => sec.id === sectionId);
    if (section) {
      section.formData[field] = value;
    }
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

  refine(sectionId: string, action: string) {
    this.reportService.refineSection(sectionId, action)?.subscribe();
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

  exportReport() {
    this.reportService.exportReport().subscribe({
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
}
