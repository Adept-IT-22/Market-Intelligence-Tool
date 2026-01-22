import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, ElementRef, ViewChild, AfterViewChecked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MarkdownModule } from 'ngx-markdown';
import { environment } from '@environments/environment';
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
  executionTime?: number;
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
  @ViewChild('queryInput') private queryInput!: ElementRef; // Reference to input for focus

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
    } catch (err) {
      console.error('Failed to scroll to bottom in MainSearchComponent.scrollToBottom:', err);
    }
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
        newThread.executionTime = res.execution_time; // Capture execution time

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

  copyResponse(content: string) {
    // Prefer modern async clipboard API when available
    if (navigator && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(content)
        .then(() => {
          // Optional: Add toast notification
        })
        .catch((err) => {
          console.error('Clipboard copy failed', err);
          window.alert('Failed to copy to clipboard. Please copy the text manually.');
        });
      return;
    }

    // Fallback for environments without navigator.clipboard
    try {
      const textarea = document.createElement('textarea');
      textarea.value = content;
      textarea.style.position = 'fixed';
      textarea.style.left = '0';
      textarea.style.top = '0';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();

      const successful = document.execCommand('copy');
      document.body.removeChild(textarea);

      if (!successful) {
        window.alert('Failed to copy to clipboard. Please copy the text manually.');
      }
    } catch (err) {
      console.error('Clipboard copy fallback failed', err);
      window.alert('Failed to copy to clipboard. Please copy the text manually.');
    }
  }

  editQuery(content: string) {
    this.query = content;
    setTimeout(() => {
      this.queryInput.nativeElement.focus();
      // this.queryInput.nativeElement.select(); // Optional: select all text
    }, 0);
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

  /**
   * Transforms file references to SharePoint URLs.
   * Handles multiple formats:
   * 1. Standard markdown: [filename](local_path)
   * 2. Source/Link format: [Source: filename | Link: path]
   * 3. Removes duplicate filenames before links
   */
  private transformReferences(text: string): string {
    // Base SharePoint URL for the document library
    const sharepointBase = 'https://adeptke.sharepoint.com/sites/ba/Shared%20Documents';

    // Local sync folder path (what gets synced to SharePoint)
    const localBasePath = 'C:\\Users\\imain\\Adept Technologies Ltd\\30. Cloud & Business Automation - Documents';
    const localBasePathAlt = 'C:/Users/imain/Adept Technologies Ltd/30. Cloud & Business Automation - Documents';

    // Helper function to convert local path to SharePoint URL
    const toSharePointUrl = (localPath: string): string => {
      let relativePath = localPath
        .replace(localBasePath, '')
        .replace(localBasePathAlt, '')
        .replace(/\\/g, '/')
        .replace(/^\//, '');

      const encodedPath = relativePath
        .split('/')
        .map((segment: string) => encodeURIComponent(segment))
        .join('/');

      return `${sharepointBase}/${encodedPath}`;
    };

    let result = text;

    // Pass 1: Handle [Source: filename | Link: path] format
    result = result.replace(/\[Source:\s*([^\|]+)\s*\|\s*Link:\s*([^\]]+)\]/g, (match, filename, localPath) => {
      const trimmedFilename = filename.trim();
      const trimmedPath = localPath.trim();
      if (trimmedPath.includes('\\') || trimmedPath.startsWith('C:')) {
        return `[${trimmedFilename}](${toSharePointUrl(trimmedPath)})`;
      }
      return `[${trimmedFilename}](${trimmedPath})`;
    });

    // Pass 2: Remove duplicate filename that appears before the markdown link
    // Pattern: "filename [filename](path)" -> "[filename](path)"
    result = result.replace(/([^\[\]]+?)\s+\[\1\]\(/g, '[$1](');

    // Pass 3: Convert standard markdown local paths to SharePoint URLs
    result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, filename, localPath) => {
      // Check if this is a local file path
      if (localPath.includes('\\') || localPath.startsWith('C:')) {
        return `[${filename}](${toSharePointUrl(localPath)})`;
      }
      // Already a URL or not a local path
      return match;
    });

    return result;
  }

  private typewriteResponse(thread: ChatThread, fullText: string) {
    // Transform the text to clean up file references
    const transformedText = this.transformReferences(fullText);
    const proxy = { value: 0 };
    const duration = Math.min(transformedText.length * 0.005, 10);

    gsap.to(proxy, {
      value: transformedText.length,
      duration: duration,
      ease: "none",
      onUpdate: () => {
        const charIndex = Math.floor(proxy.value);
        if (thread.aiMessage) {
          thread.aiMessage.content = transformedText.substring(0, charIndex);
        }
      },
      onComplete: () => {
        if (thread.aiMessage) {
          thread.aiMessage.content = transformedText;
        }
        thread.isTyping = false;
      }
    });
  }
}