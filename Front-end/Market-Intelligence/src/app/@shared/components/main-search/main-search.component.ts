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
  executionTime?: number;
  attachedFiles?: UploadedFile[];
}

interface UploadedFile {
  name: string;
  size: number;
  path: string;
  uploadedFilename: string;
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
  @ViewChild('queryInput') private queryInput!: ElementRef;
  @ViewChild('fileInput') private fileInput!: ElementRef;

  query: string = '';
  threads: ChatThread[] = [];
  attachedFiles: File[] = [];

  // Upload limits
  readonly MAX_FILE_SIZE_MB = 10;
  readonly MAX_FILE_SIZE_BYTES = this.MAX_FILE_SIZE_MB * 1024 * 1024;
  readonly ALLOWED_EXTENSIONS = ['pdf', 'docx', 'pptx', 'xlsx', 'xls', 'txt', 'csv', 'png', 'jpg', 'jpeg'];
  readonly acceptedFileTypes = this.ALLOWED_EXTENSIONS.map(ext => `.${ext}`).join(',');

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
    if (!this.query.trim() && this.attachedFiles.length === 0) return;

    // 1. Create New Thread
    const newThread: ChatThread = {
      userMessage: {
        content: this.query || `[Uploaded ${this.attachedFiles.length} file(s)]`,
        timestamp: new Date()
      },
      isLoading: true,
      loadingStep: this.loadingSteps[0],
      attachedFiles: []
    };

    this.threads.push(newThread);

    // Save context
    const distinctQuery = this.query;
    const filesToUpload = [...this.attachedFiles];
    this.query = '';
    this.attachedFiles = [];

    // Reset file input
    if (this.fileInput) {
      this.fileInput.nativeElement.value = '';
    }

    // 2. Start Loading Cycle for this specific thread
    this.cycleLoadingSteps(newThread);

    // 3. Upload files first if any
    if (filesToUpload.length > 0) {
      this.uploadFilesAndQuery(newThread, distinctQuery, filesToUpload);
    } else {
      this.executeQuery(newThread, distinctQuery);
    }
  }

  private uploadFilesAndQuery(thread: ChatThread, query: string, files: File[]) {
    const uploadPromises = files.map(file => {
      const formData = new FormData();
      formData.append('file', file);
      return this.http.post<any>(`${environment.apiUrl}/upload`, formData).toPromise();
    });

    Promise.all(uploadPromises)
      .then(results => {
        thread.attachedFiles = results.map((r, i) => ({
          name: files[i].name,
          size: files[i].size,
          path: r.path,
          uploadedFilename: r.filename
        }));

        // Now execute the query with file context
        const fileContext = thread.attachedFiles?.map(f => f.name).join(', ');
        const augmentedQuery = query ? `${query} [Attached: ${fileContext}]` : `Analyze files: ${fileContext}`;
        this.executeQuery(thread, augmentedQuery);
      })
      .catch(err => {
        console.error('File upload failed', err);
        thread.isLoading = false;
        thread.aiMessage = {
          content: `⚠️ Error uploading file: ${err.error?.error || 'Unknown error'}`,
          timestamp: new Date()
        };
      });
  }

  private executeQuery(thread: ChatThread, query: string) {
    const payload = { query };
    this.http.post(`${environment.apiUrl}/query`, payload).subscribe({
      next: (res: any) => {
        thread.isLoading = false;
        thread.isTyping = true;
        thread.executionTime = res.execution_time;

        thread.aiMessage = {
          content: '',
          timestamp: new Date()
        };

        // Trigger GSAP Typewriter
        this.typewriteResponse(thread, res.Results);
      },
      error: (err) => {
        console.error('Error fetching data', err);
        thread.isLoading = false;
        thread.aiMessage = {
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

  // ============ FILE HANDLING ============
  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;

    const file = input.files[0];

    // Validate extension
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!ext || !this.ALLOWED_EXTENSIONS.includes(ext)) {
      alert(`File type ".${ext}" not allowed. Allowed: ${this.ALLOWED_EXTENSIONS.join(', ')}`);
      input.value = '';
      return;
    }

    // Validate size
    if (file.size > this.MAX_FILE_SIZE_BYTES) {
      alert(`File too large. Maximum size: ${this.MAX_FILE_SIZE_MB}MB`);
      input.value = '';
      return;
    }

    this.attachedFiles.push(file);
    input.value = ''; // Reset to allow re-selecting same file
  }

  removeFile(index: number) {
    this.attachedFiles.splice(index, 1);
  }

  formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
}