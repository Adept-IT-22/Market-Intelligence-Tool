import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, ElementRef, ViewChild, AfterViewChecked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MarkdownModule } from 'ngx-markdown';
import { environment } from '../../../../environments/environment';
import { gsap } from 'gsap';

interface ChatMessage {
  role: 'user' | 'ai';
  content: string;
  timestamp: Date;
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
  messages: ChatMessage[] = [];
  isLoading: boolean = false;
  loadingStep: string = 'Thinking...';

  private loadingSteps = [
    "Analyzing your request...",
    "Scanning market databases...",
    "Retrieving vector context...",
    "Synthesizing insights..."
  ];

  constructor(private http: HttpClient) { }

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

    // 1. Add User Message
    const userMsg: ChatMessage = {
      role: 'user',
      content: this.query,
      timestamp: new Date()
    };
    this.messages.push(userMsg);

    // Save query for API call
    const distinctQuery = this.query;
    this.query = '';

    // 2. Set Loading State
    this.isLoading = true;
    this.cycleLoadingSteps();

    // 3. Call API
    const payload = { query: distinctQuery };
    this.http.post(`${environment.apiUrl}/query`, payload).subscribe({
      next: (res: any) => {
        this.isLoading = false;

        const aiMsg: ChatMessage = {
          role: 'ai',
          content: '',
          timestamp: new Date(),
          isTyping: true
        };
        this.messages.push(aiMsg);

        this.typewriteResponse(aiMsg, res.Results);
      },
      error: (err) => {
        console.error('Error fetching data', err);
        this.isLoading = false;
        this.messages.push({
          role: 'ai',
          content: "⚠️ Error: Could not reach the intelligence engine. Please try again later.",
          timestamp: new Date()
        });
      }
    });
  }

  private cycleLoadingSteps() {
    let stepIndex = 0;
    this.loadingStep = this.loadingSteps[0];

    // Simple interval to change loading text. 
    // In a real app with WebSocket, this would be event-driven.
    const interval = setInterval(() => {
      if (!this.isLoading) {
        clearInterval(interval);
        return;
      }
      stepIndex = (stepIndex + 1) % this.loadingSteps.length;
      this.loadingStep = this.loadingSteps[stepIndex];
    }, 2000);
  }

  private typewriteResponse(message: ChatMessage, fullText: string) {
    const proxy = { value: 0 };
    // Adjust speed based on length, max 10 seconds
    const duration = Math.min(fullText.length * 0.005, 10);

    gsap.to(proxy, {
      value: fullText.length,
      duration: duration,
      ease: "none",
      onUpdate: () => {
        const charIndex = Math.floor(proxy.value);
        message.content = fullText.substring(0, charIndex);
      },
      onComplete: () => {
        message.content = fullText;
        message.isTyping = false;
      }
    });
  }
}