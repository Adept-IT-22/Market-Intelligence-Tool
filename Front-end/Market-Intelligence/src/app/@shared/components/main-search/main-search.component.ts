import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, ElementRef, ViewChild, AfterViewChecked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MarkdownModule } from 'ngx-markdown';
import { environment } from '../../../../environments/environment';
import { gsap } from 'gsap';

interface ChatMessage {
  content: string;
  timestamp: Date;
}

interface ChatThread {
  userMessage: ChatMessage;
  aiMessage?: ChatMessage;
  isLoading?: boolean;
  loadingStep?: string;
  isTyping?: boolean;
}

@Component({
  selector: 'app-main-search',
  standalone: true,
  imports: [FormsModule, CommonModule, MarkdownModule, MatIconModule],
  templateUrl: './main-search.component.html',
  styleUrl: './main-search.component.scss'
})
export class MainSearchComponent implements AfterViewChecked {
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  query: string = '';
  threads: ChatThread[] = [];

  private loadingSteps = [
    "Analyzing your request...",
    "Scanning market databases...",
    "Retrieving vector context...",
    "Synthesizing insights..."
  ];

  constructor(private http: HttpClient) { }

  get isLoading(): boolean {
    return this.threads?.some(t => t.isLoading) ?? false;
  }

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  scrollToBottom(): void {
    try {
      if (this.scrollContainer) {
        this.scrollContainer.nativeElement.scrollTop = this.scrollContainer.nativeElement.scrollHeight;
      }
    } catch (err) { }
  }

  sendQuery() {
    if (!this.query.trim()) return;

    // 1. Create New Thread
    const newThread: ChatThread = {
      userMessage: {
        content: this.query,
        timestamp: new Date()
      },
      isLoading: true,
      loadingStep: this.loadingSteps[0]
    };

    this.threads.push(newThread);

    // Save context
    const distinctQuery = this.query;
    this.query = '';

    // 2. Start Loading Cycle for this specific thread
    this.cycleLoadingSteps(newThread);

    // 3. Call API
    const payload = { query: distinctQuery };
    this.http.post(`${environment.apiUrl}/query`, payload).subscribe({
      next: (res: any) => {
        newThread.isLoading = false;
        newThread.isTyping = true;

        newThread.aiMessage = {
          content: '',
          timestamp: new Date()
        };

        // 4. Trigger GSAP Typewriter
        this.typewriteResponse(newThread, res.Results);
      },
      error: (err) => {
        console.error('Error fetching data', err);
        newThread.isLoading = false;
        newThread.aiMessage = {
          content: "⚠️ Error: Could not reach the intelligence engine. Please try again later.",
          timestamp: new Date()
        };
      }
    });
  }

  private cycleLoadingSteps(thread: ChatThread) {
    let stepIndex = 0;

    const interval = setInterval(() => {
      if (!thread.isLoading) {
        clearInterval(interval);
        return;
      }
      stepIndex = (stepIndex + 1) % this.loadingSteps.length;
      thread.loadingStep = this.loadingSteps[stepIndex];
    }, 2000);
  }

  private typewriteResponse(thread: ChatThread, fullText: string) {
    const proxy = { value: 0 };
    const duration = Math.min(fullText.length * 0.005, 10);

    gsap.to(proxy, {
      value: fullText.length,
      duration: duration,
      ease: "none",
      onUpdate: () => {
        const charIndex = Math.floor(proxy.value);
        if (thread.aiMessage) {
          thread.aiMessage.content = fullText.substring(0, charIndex);
        }
      },
      onComplete: () => {
        if (thread.aiMessage) {
          thread.aiMessage.content = fullText;
        }
        thread.isTyping = false;
      }
    });
  }
}