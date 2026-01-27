import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, ElementRef, ViewChild, AfterViewChecked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MarkdownModule } from 'ngx-markdown';
import { environment } from '@environments/environment';
import { gsap } from 'gsap';
import { ChatService, ChatMessage as ServiceChatMessage } from '../../services/chat.service';
import { AuthService } from '../../services/auth.service';
import { effect } from '@angular/core';
import { timeout, catchError, throwError } from 'rxjs';

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

  // Cache to store threads for active/recent sessions
  private threadCache = new Map<number, ChatThread[]>();

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

  constructor(
    private http: HttpClient,
    public chatService: ChatService,
    private auth: AuthService
  ) {
    // React to session changes
    effect(() => {
      const sessionId = this.chatService.currentSessionId();
      if (sessionId) {
        // Save current threads to cache before switching if there's an active session
        // Note: The previous sessionId is not easily available in effect without extra state
        // and we usually update the cache whenever threads change anyway.

        if (this.threadCache.has(sessionId)) {
          this.threads = this.threadCache.get(sessionId)!;
          setTimeout(() => this.scrollToBottom(), 100);
        } else {
          this.loadSessionHistory(sessionId);
        }
      } else {
        this.threads = [];
      }
    });
  }

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

    // 1. If no session exists, create one first (works for both Auth and Guest)
    if (!this.chatService.currentSessionId()) {
      const initialQuery = this.query;
      const initialFiles = [...this.attachedFiles];

      this.chatService.createSession(initialQuery.substring(0, 50) || 'New Chat').subscribe((res: any) => {
        // Continue with the newly created session
        this.processNewQuery(initialQuery, initialFiles);
      });
      this.query = '';
      this.attachedFiles = [];
      return;
    }

    this.processNewQuery(this.query, this.attachedFiles);
    this.query = '';
    this.attachedFiles = [];
  }

  private processNewQuery(queryText: string, files: File[]) {
    const newThread: ChatThread = {
      userMessage: {
        content: queryText || `[Uploaded ${files.length} file(s)]`,
        timestamp: new Date()
      },
      isLoading: true,
      loadingStep: this.loadingSteps[0],
      attachedFiles: []
    };

    this.threads.push(newThread);

    // Reset UI
    if (this.fileInput) {
      this.fileInput.nativeElement.value = '';
    }

    this.cycleLoadingSteps(newThread);

    const sessionId = this.chatService.currentSessionId();
    if (sessionId) {
      this.threadCache.set(sessionId, this.threads);
    }

    if (files.length > 0) {
      this.uploadFilesAndQuery(newThread, queryText, files);
    } else {
      this.executeQuery(newThread, queryText);
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
    const sessionId = this.chatService.currentSessionId();
    const payload = {
      query,
      session_id: sessionId
    };

    this.http.post(`${environment.apiUrl}/query`, payload, {
      headers: { 'Authorization': `Bearer ${this.auth.getToken()}` }
    })
      .pipe(
        timeout(120000), // 120 seconds timeout for slow backend processing
        catchError((err) => {
          if (err.name === 'TimeoutError') {
            return throwError(() => ({ error: { error: 'Request timed out. The system is taking longer than expected. Please try again.' } }));
          }
          return throwError(() => err);
        })
      )
      .subscribe({
        next: (res: any) => {
          thread.isLoading = false;
          thread.isTyping = true;
          thread.executionTime = res.execution_time;

          thread.aiMessage = {
            content: '',
            timestamp: new Date()
          };

          this.typewriteResponse(thread, res.Results);

          // For guests, save messages to localStorage
          if (sessionId && sessionId < 0) {
            this.chatService.saveGuestMessage(sessionId, {
              role: 'user',
              content: query
            });
            this.chatService.saveGuestMessage(sessionId, {
              role: 'assistant',
              content: res.Results,
              execution_time: res.execution_time
            });
          }

          // Auto-rename chat if it's the first message and title is "New Chat"
          if (sessionId && this.threads.length === 1) {
            const currentSessions = this.chatService.sessions();
            const session = currentSessions.find(s => s.id === sessionId);
            if (session && session.title === 'New Chat') {
              // Use a short summary of the result or the query as name
              const newTitle = query.length > 30 ? query.substring(0, 30) + '...' : query;
              this.chatService.renameChat(sessionId, newTitle).subscribe();
            }
          }
        },
        error: (err) => {
          console.error('Error fetching data', err);
          thread.isLoading = false;
          const errorMsg = err?.error?.error || err?.message || 'Could not reach the intelligence engine. Please try again later.';
          thread.aiMessage = {
            content: `⚠️ Error: ${errorMsg}`,
            timestamp: new Date()
          };
        }
      });

    // Update cache because threads array reference might change or items might be added
    if (sessionId) {
      this.threadCache.set(sessionId, this.threads);
    }
  }

  private loadSessionHistory(sessionId: number) {
    this.chatService.getChatDetails(sessionId).subscribe((res: any) => {
      const historyThreads: ChatThread[] = [];

      // Group API messages into user/assistant pairs for the UI
      for (let i = 0; i < res.messages.length; i++) {
        const msg = res.messages[i];
        if (msg.role === 'user') {
          const nextMsg = res.messages[i + 1];
          historyThreads.push({
            userMessage: {
              content: msg.content,
              timestamp: new Date(msg.created_at || Date.now())
            },
            aiMessage: nextMsg?.role === 'assistant' ? {
              content: nextMsg.content,
              timestamp: new Date(nextMsg.created_at || Date.now())
            } : undefined,
            executionTime: nextMsg?.execution_time,
            isLoading: false,
            isTyping: false
          });
          if (nextMsg?.role === 'assistant') i++;
        }
      }
      this.threads = historyThreads;
      this.threadCache.set(sessionId, historyThreads);
      setTimeout(() => this.scrollToBottom(), 100);
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
    result = result.replace(/\[Source:\s*([^|]+)\s*\|\s*Link:\s*([^\]]+)\]/g, (match, filename, localPath) => {
      const trimmedFilename = filename.trim();
      const trimmedPath = localPath.trim();
      if (trimmedPath.includes('\\') || trimmedPath.startsWith('C:')) {
        return `[${trimmedFilename}](${toSharePointUrl(trimmedPath)})`;
      }
      return `[${trimmedFilename}](${trimmedPath})`;
    });

    // Pass 2: Remove duplicate filename that appears before the markdown link
    // Pattern: "filename [filename](path)" -> "[filename](path)"
    result = result.replace(/([^\[\]]+?)\s+\[([^\]]+)\]\(/g, (match, before, inBrackets) => {
      // Only remove the leading text if it matches the text inside the brackets
      if (before.trim() === inBrackets.trim()) {
        return `[${inBrackets}](`;
      }
      return match;
    });

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