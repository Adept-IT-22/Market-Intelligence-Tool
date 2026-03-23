import { CommonModule, isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, ElementRef, ViewChild, AfterViewChecked, PLATFORM_ID, Inject } from '@angular/core';
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
  isCached?: boolean;
  attachedFiles?: UploadedFile[];
  isCachedResult?: boolean;
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
    "Synthesizing insights...",
    "Consulting Adept R&D archives...",
    "Processing economic indicators...",
    "Mapping industry trends...",
    "Validating data points..."
  ];

  private contextLoadingSteps: { [key: string]: string[] } = {
    adept: [
      "Accessing Adept project database...",
      "Retrieving innovation timelines...",
      "Analyzing system architecture..."
    ],
    market: [
      "Scanning Kenyan market sectors...",
      "Evaluating economic sentiment...",
      "Filtering financial data..."
    ],
    innovation: [
      "Researching internal IPs...",
      "Synthesizing breakthrough insights...",
      "Reviewing R&D collateral..."
    ]
  };

  // Onboarding modal
  showOnboarding: boolean = false;
  demoQueries = {
    adept: "What innovation projects is Adept Technologies currently working on?",
    market: "What are Kenya's key economic sectors and their growth trends?",
    mixed: "How could Adept's chatbot innovation be applied to analyze Kenyan market sentiment?"
  };

  constructor(
    private http: HttpClient,
    public chatService: ChatService,
    private auth: AuthService,
    @Inject(PLATFORM_ID) private platformId: Object
  ) {
    // Check if user has seen onboarding (only in browser, not during SSR)
    if (isPlatformBrowser(this.platformId)) {
      const hasSeenOnboarding = localStorage.getItem('mit_hasSeenOnboarding');
      this.showOnboarding = !hasSeenOnboarding;
    }

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

    this.cycleLoadingSteps(newThread, queryText);

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

    // --- No cache hit, call server with Streaming enabled ---
    const payload = {
      query,
      session_id: sessionId,
      stream: true // Enable streaming
    };

    thread.aiMessage = {
      content: '',
      timestamp: new Date()
    };

    fetch(`${environment.apiUrl}/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.auth.getToken()}`
      },
      body: JSON.stringify(payload)
    })
      .then(async response => {
        if (!response.ok) {
          const err = await response.json();
          throw new Error(err.error || 'Server error');
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('ReadableStream not supported');

        thread.isLoading = false;
        thread.isTyping = true;
        let fullResponse = '';
        let buffer = '';

        const decoder = new TextDecoder();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep partial line in buffer

          for (const line of lines) {
            const trimmedLine = line.trim();
            if (trimmedLine.startsWith('data: ')) {
              try {
                const data = JSON.parse(trimmedLine.substring(6));
                if (data.chunk) {
                  fullResponse += data.chunk;
                  // Update UI in real-time
                  if (thread.aiMessage) {
                    thread.aiMessage.content = this.transformReferences(fullResponse);
                  }
                  this.scrollToBottom();
                } else if (data.done) {
                  thread.executionTime = data.execution_time;
                  thread.isTyping = false;

                }
              } catch (e) {
                console.warn('Error parsing SSE chunk', e);
              }
            }
          }
        }

        // For guests, save messages to localStorage after stream ends
        if (sessionId && sessionId < 0) {
          this.chatService.saveGuestMessage(sessionId, { role: 'user', content: query });
          this.chatService.saveGuestMessage(sessionId, {
            role: 'assistant', content: fullResponse, execution_time: thread.executionTime
          });
        }

        // Auto-rename chat if it's the first message
        if (sessionId && this.threads.length === 1) {
          const session = this.chatService.sessions().find(s => s.id === sessionId);
          if (session && session.title === 'New Chat') {
            const newTitle = query.length > 30 ? query.substring(0, 30) + '...' : query;
            this.chatService.renameChat(sessionId, newTitle).subscribe();
          }
        }
      })
      .catch(err => {
        console.error('Streaming error', err);
        thread.isLoading = false;
        thread.isTyping = false;
        const errorMsg = err?.message || 'Could not reach the intelligence engine.';
        thread.aiMessage = {
          content: `⚠️ Error: ${errorMsg}`,
          timestamp: new Date()
        };
      });

    // Update cache because threads array reference might change
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

  private cycleLoadingSteps(thread: ChatThread, query?: string) {
    let stepIndex = 0;
    let pool = [...this.loadingSteps];

    // Add query-specific steps if applicable
    if (query) {
      const q = query.toLowerCase();
      if (q.includes('adept') || q.includes('system') || q.includes('project')) {
        pool = [...this.contextLoadingSteps['adept'], ...pool];
      } else if (q.includes('market') || q.includes('kenya') || q.includes('economy')) {
        pool = [...this.contextLoadingSteps['market'], ...pool];
      } else if (q.includes('innovation') || q.includes('creative') || q.includes('new')) {
        pool = [...this.contextLoadingSteps['innovation'], ...pool];
      }
    }

    thread.loadingStep = pool[0];

    const interval = setInterval(() => {
      if (!thread.isLoading) {
        clearInterval(interval);
        return;
      }
      stepIndex = (stepIndex + 1) % pool.length;
      thread.loadingStep = pool[stepIndex];
    }, 1800); // Slightly faster cycle for more realism
  }

  /**
   * Transforms file references to SharePoint URLs.
   * Converts local paths to clickable SharePoint links while keeping clean filenames.
   * Format: [filename.pdf](C:\...) becomes [filename.pdf](https://sharepoint.com/...)
   */
  private transformReferences(text: string): string {
    let result = text;

    // Common base path for all Adept folders
    const localUserBase = 'C:\\Users\\imain\\Adept Technologies Ltd\\';
    const localUserBaseAlt = 'C:/Users/imain/Adept Technologies Ltd/';

    // SharePoint mappings for different folders
    const sharePointMappings: { [key: string]: string } = {
      '30. Cloud & Business Automation - Documents': 'https://adeptke.sharepoint.com/sites/ba/Shared%20Documents',
      '03. Marketing - General': 'https://adeptke.sharepoint.com/sites/Adepttechnologiesltd/Shared%20Documents/03.%20Marketing%20-%20General',
      '36. BD Collateral - General': 'https://adeptke.sharepoint.com/sites/Adepttechnologiesltd/Shared%20Documents/36.%20BD%20Collateral%20-%20General',
      'Innovations - General': 'https://adeptke.sharepoint.com/sites/Adepttechnologiesltd/Shared%20Documents/Innovations%20-%20General'
    };

    // Helper to extract just the filename from a full path
    const extractFilename = (path: string): string => {
      const parts = path.replace(/\\/g, '/').split('/');
      return parts[parts.length - 1] || path;
    };

    // Helper to check if a path is a local Windows path
    const isLocalPath = (path: string): boolean => {
      return path.includes('\\') ||
        path.startsWith('C:') ||
        path.startsWith('D:') ||
        path.includes('/Users/') ||
        path.includes('\\Users\\');
    };

    // Helper to convert local path to SharePoint URL
    const toSharePointUrl = (localPath: string): string => {
      // Normalize path
      let normalizedPath = localPath.replace(/\\/g, '/');

      // Remove the base user path
      normalizedPath = normalizedPath
        .replace(localUserBase.replace(/\\/g, '/'), '')
        .replace(localUserBaseAlt, '');

      // Find which SharePoint folder this belongs to
      for (const [folderName, sharePointBase] of Object.entries(sharePointMappings)) {
        if (normalizedPath.startsWith(folderName)) {
          // Extract the relative path after the folder name
          const relativePath = normalizedPath.substring(folderName.length).replace(/^\//, '');

          if (!relativePath) {
            return sharePointBase;
          }

          // Encode each segment
          const encodedPath = relativePath
            .split('/')
            .map((segment: string) => encodeURIComponent(segment))
            .join('/');

          return `${sharePointBase}/${encodedPath}`;
        }
      }

      // Fallback: no mapping found; avoid exposing local paths
      console.warn('No SharePoint mapping found for local path:', localPath);
      return '#'; // Return placeholder to prevent path exposure
    };

    // Pass 1: Handle [Source: filename | Link: path] format
    result = result.replace(/\[Source:\s*([^|]+)\s*\|\s*Link:\s*([^\]]+)\]/g, (match, filename, localPath) => {
      const trimmedFilename = filename.trim();
      const cleanPath = localPath.trim();

      // Fix "route_" or internal names appearing as filename
      const displayFilename = (trimmedFilename.startsWith('route_') || trimmedFilename.startsWith('detail_'))
        ? extractFilename(cleanPath)
        : trimmedFilename;

      if (isLocalPath(cleanPath)) {
        const sharePointUrl = toSharePointUrl(cleanPath);
        return `[${displayFilename}](${sharePointUrl})`;
      }
      return `[${displayFilename}](${cleanPath})`;
    });

    // Pass 2: Remove duplicate filename that appears before the markdown link
    result = result.replace(/([^\[\]]+?)\s+\[([^\]]+)\]\(/g, (match, before, inBrackets) => {
      const trimmedBefore = before.trim();
      const trimmedInBrackets = inBrackets.trim();
      if (trimmedBefore === trimmedInBrackets || (trimmedInBrackets.startsWith('route_') && trimmedBefore)) {
        return `[${trimmedInBrackets === 'route_*' ? trimmedBefore : trimmedInBrackets}](`;
      }
      return match;
    });

    // Pass 3: Convert markdown links with local paths to SharePoint URLs
    result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, filename, path) => {
      const cleanFilename = (filename.startsWith('route_') || filename.startsWith('detail_'))
        ? extractFilename(path)
        : filename;

      if (isLocalPath(path)) {
        const sharePointUrl = toSharePointUrl(path);
        return `[${cleanFilename}](${sharePointUrl})`;
      }
      // Keep web URLs as-is
      return match;
    });

    // Pass 4: Clean up any remaining raw Windows-style paths in the text (convert to bold filenames)
    result = result.replace(/[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*/g, (match) => {
      const filename = extractFilename(match);
      return `**${filename}**`;
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

  // ============ ONBOARDING MODAL ============
  closeOnboarding() {
    this.showOnboarding = false;
    if (isPlatformBrowser(this.platformId)) {
      localStorage.setItem('mit_hasSeenOnboarding', 'true');
    }
  }

  useDemoQuery(demoQuery: string) {
    this.query = demoQuery;
    this.closeOnboarding();
    // Execute query immediately after modal closes
    this.sendQuery();
  }
}