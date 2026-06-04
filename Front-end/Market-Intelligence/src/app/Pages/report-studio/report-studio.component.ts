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
  public brandLogoUi = '/whiteadeptlogo.png';
  public brandSidebar = '/adept_sidebar.png';
  public brandFooter = '/adept_footer.png';
  
  public get currentMonthYear(): string {
    const s = this.state();
    const metadata = this.getSectionById(s, 'metadata');
    if (metadata) {
      const fd = metadata.formData || {};
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
    { id: 'software_engineering', name: 'Software Engineering' },
    { id: 'finance', name: 'Finance & Operations' },
    { id: 'marketing', name: 'Marketing & Comms' },
    { id: 'call_centre', name: 'Call Centre' },
    { id: 'sales', name: 'Sales & Business Development' }
  ];

  public selectedType = signal('software_engineering');
  public editingSectionId = signal<string | null>(null);
  public dismissedInsights = signal<string[]>([]);
  public activeAccepts = signal<Record<string, boolean>>({});

  dismissInsight(text: string, event?: Event) {
    if (event) {
      event.stopPropagation();
    }
    this.dismissedInsights.update(curr => [...curr, text]);
  }

  isDismissed(text: string): boolean {
    return this.dismissedInsights().includes(text);
  }

  acceptSuggestion(targetId: string, text: string, event?: Event) {
    if (event) {
      event.stopPropagation();
    }
    const s = this.state();
    const section = s?.sections.find(sec => sec.id === targetId);
    if (section) {
      const currentText = section.userOverride ?? section.aiDraft ?? '';
      this.saveHistory(targetId, currentText);
    }
    this.activeAccepts.update(curr => ({ ...curr, [text]: true }));
    this.reportService.applyAdvisorSuggestion(targetId, text)?.subscribe({
      next: () => {
        this.dismissInsight(text);
        this.activeAccepts.update(curr => ({ ...curr, [text]: false }));
      },
      error: (err) => {
        console.error('Failed to apply suggestion', err);
        this.activeAccepts.update(curr => ({ ...curr, [text]: false }));
      }
    });
  }

  startEditingTitle(id: string) {
    this.editingSectionId.set(id);
    setTimeout(() => {
      const el = document.querySelector('.title-edit-input, .step-title-input') as HTMLInputElement;
      if (el) {
        el.focus();
        el.select();
      }
    }, 50);
  }

  saveTitle(id: string, event: any) {
    const newTitle = event.target.value.trim();
    if (newTitle && this.editingSectionId() === id) {
      this.reportService.updateSectionTitle(id, newTitle);
    }
    this.editingSectionId.set(null);
  }

  cancelEditingTitle() {
    this.editingSectionId.set(null);
  }

  ngOnInit() {
    this.loadSchema('software_engineering');
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

    if (s.type === 'software_engineering') {
      const sprintGoal = 'Deliver a functional Market Intelligence MVP module with:\n- Completed frontend dashboard views\n- Integrated report generation (Report Studio)\n- Initial data pipeline validation';
      const sprintScope = 'This sprint focused on transitioning Manuh from UI completion → functional analytics system.\n\nIncluded:\n- Dashboard UI finalization\n- Report Studio implementation\n- Basic data flow integration (mock/live hybrid)\n\nExcluded:\n- Advanced analytics models\n- Full production deployment\n- External API integrations';
      const introText = 'Core system components were successfully built and integrated. However, deployment and full system validation remain incomplete, pushing critical tasks into the next sprint. The team is focusing on stabilization and environment readiness.';
      const statusRating = 'Delayed';
      const statusSummary = 'We are currently in a **Delayed** state due to environment provisioning bottlenecks. While technical development is 90% complete, the integration validation phase requires a stable production-like environment which is pending approval.';
      const timeline = 'April 8 – April 22, 2026';
      const timeSpent = '167 hours';
      const tasksCompleted = '- **Analytics Dashboard:** Completed all UI components and partial data binding.\n- **Report Studio:** End-to-end workflow implemented (create, preview, export).\n- **API Integration:** Core frontend-backend communication endpoints are operational.';
      const futureTasks = '- **Server Deployment:** Critical task pushed to next sprint.\n- **Advanced Models:** Integration of predictive analytics.\n- **External APIs:** Finalizing third-party data connectors.';
      const qaMetrics = '- **Test Coverage:** 84% unit test coverage achieved.\n- **Bugs Identified:** 12 minor UI glitches found (fixed).\n- **Performance:** Average response time < 200ms for core dashboards.';
      const testResults = '- Unit tests completed successfully\n- Integration tests passing';
      const issueList = '- **Deployment:** Awaiting production environment provisioning.\n- **Validation:** Full end-to-end system testing delayed by 2 days.';
      const pendingApprovals = '- **Production Environment:** Critical sign-off needed by end of week.\n- **Security Audit:** Initial findings require remediation before live deployment.\n- **User Acceptance:** Scheduled for the first week of May.';

      // Metadata
      this.onFormChange('metadata', 'project_name', 'Manuh Market Intelligence Platform');
      this.onFormChange('metadata', 'report_by', 'Emmanuel Mwendia Maina');
      this.onFormChange('metadata', 'sprint_no', 4);
      this.onFormChange('metadata', 'period', new Date('2026-04-22'));
      this.onFormChange('metadata', 'sprint_goal', sprintGoal);
      this.onFormChange('metadata', 'sprint_scope', sprintScope);

      // Form inputs
      this.onFormChange('intro', 'executive_summary', introText);
      this.onFormChange('status', 'status_rating', statusRating);
      this.onFormChange('status', 'summary_text', statusSummary);
      this.onFormChange('status', 'timeline', timeline);
      this.onFormChange('status', 'time_spent', timeSpent);
      this.onFormChange('progress_detail', 'tasks_completed', tasksCompleted);
      this.onFormChange('next_sprint', 'future_tasks', futureTasks);
      this.onFormChange('qa', 'qa_metrics', qaMetrics);
      this.onFormChange('qa', 'test_results', testResults);
      this.onFormChange('issues', 'issue_list', issueList);
      this.onFormChange('next_steps', 'pending_approvals', pendingApprovals);

      // Section Drafts
      this.reportService.updateSectionDraft('intro', '#### Executive Summary\n' + introText);
      this.reportService.updateSectionDraft('status', '#### Overall Status Summary\n' + statusSummary);
      this.reportService.updateSectionDraft('progress_detail', '#### Key Accomplishments\n' + tasksCompleted);
      this.reportService.updateSectionDraft('next_sprint', '#### Upcoming Priorities\n' + futureTasks);
      this.reportService.updateSectionDraft('qa', '#### QA Metrics & Findings\n' + qaMetrics + '\n\n' + testResults);
      this.reportService.updateSectionDraft('issues', '#### Current Blockers\n' + issueList);
      this.reportService.updateSectionDraft('next_steps', '#### Required Approvals\n' + pendingApprovals);

    } else if (s.type === 'marketing') {
      const channels = '- LinkedIn Sponsored Content\n- Google Search Ads (Targeted)\n- Tech Industry Partner Newsletters\n- Organic SEO and Blogs';
      const messaging = 'Focus on time savings (60% reduction in reporting time) and business intelligence capabilities.';
      const kpis = 'Goal: Increase inbound qualified leads by 20% in Q2.';
      const budget = '$45,000';
      const leads = 1250;
      const conversionRate = '3.4%';
      const campaignsSummary = 'LinkedIn Ads campaign outperformed benchmarks, generating 800+ leads at a lower cost-per-lead (CPL) than previous quarters. Newsletter placements drove high quality enterprise trials.';

      // Metadata
      this.onFormChange('metadata', 'campaign_name', 'Q2 Growth Campaign');
      this.onFormChange('metadata', 'report_by', 'Sarah Jenkins (Marketing Director)');
      this.onFormChange('metadata', 'period', 'April 1 – June 30, 2026');
      this.onFormChange('metadata', 'target_audience', 'Enterprise Tech Leaders & Decision Makers');

      // Form inputs
      this.onFormChange('strategy', 'channels', channels);
      this.onFormChange('strategy', 'messaging', messaging);
      this.onFormChange('performance', 'kpis', kpis);
      this.onFormChange('performance', 'budget', budget);
      this.onFormChange('performance', 'leads', leads);
      this.onFormChange('performance', 'conversion_rate', conversionRate);
      this.onFormChange('performance', 'campaigns_summary', campaignsSummary);

      // Section Drafts
      this.reportService.updateSectionDraft('strategy', '#### Marketing Strategy\n- **Channels Used:**\n' + channels + '\n- **Core Messaging:**\n' + messaging);
      this.reportService.updateSectionDraft('performance', '#### Execution & Performance\n- **KPIs:** ' + kpis + '\n- **Budget Spent:** ' + budget + '\n- **Leads Generated:** ' + leads + '\n- **Conversion Rate:** ' + conversionRate + '\n- **Campaigns Summary:**\n' + campaignsSummary);

    } else if (s.type === 'finance') {
      const revenue = '$182,500';
      const expenses = '$124,000';
      const cashFlow = 'Highly positive cash flow (+58,500 net surplus) driven by corporate renewals and successful expansion deals.';
      const opsHighlights = '✅ Migrated customer billing system to automated invoicing\n✅ Reduced office overhead costs by 8%\n✅ Finalized third-party vendor audits';
      const resourceUtil = 'Engineering and consulting teams are at 92% utilization rate. Core resources are allocated to MVP launch.';
      const costOutliers = '- Server hosting costs (+14% above projection)\n- Audit consulting fees (one-off expense)';
      const mitigations = 'Applying auto-scaling rules on Qdrant and GPU servers during off-peak hours to reduce monthly hosting costs by 10%.';

      // Metadata
      this.onFormChange('metadata', 'department', 'Finance & Operations');
      this.onFormChange('metadata', 'report_by', 'David Kimani (CFO)');
      this.onFormChange('metadata', 'period', 'May 2026');

      // Form inputs
      this.onFormChange('financial_status', 'revenue', revenue);
      this.onFormChange('financial_status', 'expenses', expenses);
      this.onFormChange('financial_status', 'cash_flow', cashFlow);
      this.onFormChange('operations', 'ops_highlights', opsHighlights);
      this.onFormChange('operations', 'resource_util', resourceUtil);
      this.onFormChange('risks', 'cost_outliers', costOutliers);
      this.onFormChange('risks', 'mitigations', mitigations);

      // Section Drafts
      this.reportService.updateSectionDraft('financial_status', '#### Financial Health\n- **Revenue:** ' + revenue + '\n- **Expenses:** ' + expenses + '\n- **Cash Flow Summary:**\n' + cashFlow);
      this.reportService.updateSectionDraft('operations', '#### Operational Efficiency\n- **Highlights:**\n' + opsHighlights + '\n- **Resource Utilization:**\n' + resourceUtil);
      this.reportService.updateSectionDraft('risks', '#### Financial Risks & Cost Control\n- **Outliers:**\n' + costOutliers + '\n- **Mitigations:**\n' + mitigations);

    } else if (s.type === 'call_centre') {
      const totalCalls = 14820;
      const slaPercentage = '94.2% (Target: 95.0%)';
      const aht = '3m 45s';
      const abandonmentRate = '2.1%';
      const csat = '4.6 / 5.0';
      const topAgents = '- Mercy W.\n- John D.\n- Peter K.';
      const qaScore = '91.5%';
      const peakTimes = '10:00 AM – 12:30 PM, 2:00 PM – 4:30 PM (Mon-Wed)';
      const complaints = '- Portal login loading times\n- Invoicing statement clarity\n- Feature request questions';
      const downtime = '12 minutes total downtime scheduled for database security patching.';

      // Metadata
      this.onFormChange('metadata', 'queue_name', 'Customer Care Tier-1');
      this.onFormChange('metadata', 'report_by', 'Angela Mutua (Call Centre Manager)');
      this.onFormChange('metadata', 'period', 'May 2026');

      // Form inputs
      this.onFormChange('call_metrics', 'total_calls', totalCalls);
      this.onFormChange('call_metrics', 'sla_percentage', slaPercentage);
      this.onFormChange('call_metrics', 'aht', aht);
      this.onFormChange('call_metrics', 'abandonment_rate', abandonmentRate);
      this.onFormChange('agent_performance', 'csat', csat);
      this.onFormChange('agent_performance', 'top_agents', topAgents);
      this.onFormChange('agent_performance', 'qa_score', qaScore);
      this.onFormChange('call_trends', 'peak_times', peakTimes);
      this.onFormChange('call_trends', 'complaints', complaints);
      this.onFormChange('call_trends', 'downtime', downtime);

      // Section Drafts
      this.reportService.updateSectionDraft('call_metrics', '#### Call Performance\n- **Total Calls:** ' + totalCalls + '\n- **SLA Achieved:** ' + slaPercentage + '\n- **Average Handle Time:** ' + aht + '\n- **Abandonment Rate:** ' + abandonmentRate);
      this.reportService.updateSectionDraft('agent_performance', '#### Agent & CSAT Details\n- **CSAT Score:** ' + csat + '\n- **Top Performing Agents:**\n' + topAgents + '\n- **QA Score Average:** ' + qaScore);
      this.reportService.updateSectionDraft('call_trends', '#### Call Volume Trends & Core Issues\n- **Peak Volumes/Times:** ' + peakTimes + '\n- **Common Customer Issues:**\n' + complaints + '\n- **System Downtime Details:**\n' + downtime);

    } else if (s.type === 'sales') {
      const newLeads = 145;
      const pipelineDeals = '- Safaricom Expansion\n- KCB Group Core Contract\n- Equity Bank Pilot Engagement';
      const pipelineVal = '$320,000';
      const closedRev = '$115,000';
      const keyWon = '- KCB Group Core Contract ($85K)\n- Safaricom Pilot Phase ($30K)';
      const conversionRate = '18.5%';
      const competitors = 'Oracle Cloud and local custom software consulting agencies.';
      const salesHurdles = '- Extended procurement cycles in corporate banking\n- Complex IT security reviews';
      const stalledDealsNext = 'Scheduling technical architecture walkthroughs directly with banking CISO teams to accelerate compliance approvals.';

      // Metadata
      this.onFormChange('metadata', 'territory', 'East Africa Enterprise Accounts');
      this.onFormChange('metadata', 'report_by', 'Ken Mwangi (Head of Business Development)');
      this.onFormChange('metadata', 'period', 'May 2026');

      // Form inputs
      this.onFormChange('pipeline', 'new_leads', newLeads);
      this.onFormChange('pipeline', 'pipeline_deals', pipelineDeals);
      this.onFormChange('pipeline', 'pipeline_val', pipelineVal);
      this.onFormChange('closed_deals', 'closed_rev', closedRev);
      this.onFormChange('closed_deals', 'key_won', keyWon);
      this.onFormChange('closed_deals', 'conversion_rate', conversionRate);
      this.onFormChange('strategy_challenges', 'competitors', competitors);
      this.onFormChange('strategy_challenges', 'sales_hurdles', salesHurdles);
      this.onFormChange('strategy_challenges', 'stalled_deals_next', stalledDealsNext);

      // Section Drafts
      this.reportService.updateSectionDraft('pipeline', '#### Sales Pipeline Status\n- **New Leads Qualified:** ' + newLeads + '\n- **Deals in Pipeline:**\n' + pipelineDeals + '\n- **Pipeline Value:** ' + pipelineVal);
      this.reportService.updateSectionDraft('closed_deals', '#### Closed Revenue & Conversions\n- **Revenue Closed:** ' + closedRev + '\n- **Key Accounts Won:**\n' + keyWon + '\n- **Sales Conversion Rate:** ' + conversionRate);
      this.reportService.updateSectionDraft('strategy_challenges', '#### BD Strategy & Market Challenges\n- **Competitor Insights:** ' + competitors + '\n- **Current Sales Hurdles:**\n' + salesHurdles + '\n- **Next Steps for Stalled Deals:**\n' + stalledDealsNext);
    }
    this.reportService.analyzeReport();
  }

  clearDemoData() {
    const s = this.state();
    if (!s) return;
    
    const type = s.type;
    const title = this.reportTypes.find(t => t.id === type)?.name || 'New Report';
    const schema = this.sectionSchema();
    
    // Reset report state
    this.reportService.initReport(type, title, schema);
    
    // Clear advisor state in component
    this.dismissedInsights.set([]);
    this.activeAccepts.set({});
    this.draftHistory.clear();
  }

  // History tracking for undo/redo
  private draftHistory = new Map<string, { past: string[]; future: string[] }>();

  private getHistory(sectionId: string) {
    if (!this.draftHistory.has(sectionId)) {
      this.draftHistory.set(sectionId, { past: [], future: [] });
    }
    return this.draftHistory.get(sectionId)!;
  }

  saveHistory(sectionId: string, currentText: string) {
    const history = this.getHistory(sectionId);
    history.past.push(currentText);
    history.future = []; // Clear redo stack on new change
  }

  canUndo(sectionId: string): boolean {
    const history = this.draftHistory.get(sectionId);
    return !!(history && history.past.length > 0);
  }

  canRedo(sectionId: string): boolean {
    const history = this.draftHistory.get(sectionId);
    return !!(history && history.future.length > 0);
  }

  undo(sectionId: string) {
    const history = this.draftHistory.get(sectionId);
    if (!history || history.past.length === 0) return;

    const s = this.state();
    const section = s?.sections.find(sec => sec.id === sectionId);
    if (!section) return;

    const currentText = section.userOverride ?? section.aiDraft ?? '';
    const previousText = history.past.pop()!;
    history.future.push(currentText);

    this.reportService.updateUserOverride(sectionId, previousText);
  }

  redo(sectionId: string) {
    const history = this.draftHistory.get(sectionId);
    if (!history || history.future.length === 0) return;

    const s = this.state();
    const section = s?.sections.find(sec => sec.id === sectionId);
    if (!section) return;

    const currentText = section.userOverride ?? section.aiDraft ?? '';
    const nextText = history.future.pop()!;
    history.past.push(currentText);

    this.reportService.updateUserOverride(sectionId, nextText);
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
    const s = this.state();
    const section = s?.sections.find(sec => sec.id === sectionId);
    if (section) {
      const currentText = section.userOverride ?? section.aiDraft ?? '';
      this.saveHistory(sectionId, currentText);
    }
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
    const s = this.state();
    const section = s?.sections.find(sec => sec.id === sectionId);
    if (section) {
      const currentText = section.userOverride ?? section.aiDraft ?? '';
      if (currentText !== text) {
        this.saveHistory(sectionId, currentText);
        this.reportService.updateUserOverride(sectionId, text);
      }
    }
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

  getSectionById(s: ReportState | null, id: string): SectionState | null {
    if (!s || !s.sections) return null;
    return s.sections.find(sec => sec.id === id) || null;
  }

  getDisplayTitle(s: ReportState | null): string {
    const metadata = this.getSectionById(s, 'metadata');
    if (!metadata) return '';
    const formData = metadata.formData || {};
    let title = formData['project_name'] || formData['campaign_name'] || s?.title || '';
    
    // If title is an object, extract a string property
    if (typeof title === 'object' && title !== null) {
      title = (title as any).value || (title as any).name || (title as any).text || (title as any).content || 'New Report';
    }
    
    return String(title);
  }

  getMetadata(s: ReportState | null) {
    const metadata = this.getSectionById(s, 'metadata');
    if (!metadata) return null;
    const formData = metadata.formData || {};
    return {
      project: formData['project_name'] || 'Market Intelligence',
      preparedBy: formData['prepared_by'] || 'Adept Studio',
      date: formData['reporting_date'] || this.currentMonthYear,
      type: this.reportTypes.find(t => t.id === s?.type)?.name || 'Strategic Report'
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

  getSplitIntro(s: ReportState | null, part: 1 | 2): string {
    const intro = this.getSectionById(s, 'intro');
    if (!intro) return '';
    const text = intro.userOverride ?? intro.aiDraft ?? '';
    
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
    return this.getSplitIntro(s, 2).trim().length > 0;
  }

  shouldBreakOverallStatus(s: ReportState | null): boolean {
    if (!s || !s.sections) return false;
    
    // Always break if the Intro is already splitting onto two pages
    if (this.shouldSplitIntro(s)) return true;

    // Check the Intro content length (both form data and AI draft)
    const intro = this.getSectionById(s, 'intro');
    const introLen = intro ? Math.max(
      (intro.formData?.['executive_summary'] || '').length,
      (intro.userOverride ?? intro.aiDraft ?? '').length
    ) : 0;

    // Check the Status content length
    const status = this.getSectionById(s, 'status');
    const statusLen = status ? Math.max(
      (status.formData?.['summary_text'] || '').length,
      (status.userOverride ?? status.aiDraft ?? '').length
    ) : 0;
    
    // If combined visible content is substantial, break to new page
    return (introLen + statusLen) > 300; // Increased threshold for AI drafts
  }

  shouldBreakIssues(s: ReportState | null): boolean {
    return this.getSplitIssues(s, 2).trim().length > 0;
  }

  getSplitIssues(s: ReportState | null, part: 1 | 2): string {
    const issues = this.getSectionById(s, 'issues');
    if (!issues) return '';
    const text = issues.userOverride ?? issues.aiDraft ?? '';
    
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

  hasVisibleInsights(items: any[] | undefined): boolean {
    if (!items) return false;
    return items.some(item => !this.isDismissed(item.text));
  }

  hasAnalysis(s: ReportState | null): boolean {
    if (!s || !s.analysis) return false;
    return this.hasVisibleInsights(s.analysis.risks) ||
      this.hasVisibleInsights(s.analysis.inconsistencies) ||
      this.hasVisibleInsights(s.analysis.suggestions);
  }
}
