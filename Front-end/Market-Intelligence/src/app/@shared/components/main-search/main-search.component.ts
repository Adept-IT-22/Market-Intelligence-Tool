import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MarkdownModule } from 'ngx-markdown';
import { environment } from '../../../../environments/environment';

@Component({
  selector: 'app-main-search',
  standalone: true,
  imports: [FormsModule, CommonModule, MarkdownModule, MatIconModule],
  templateUrl: './main-search.component.html',
  styleUrl: './main-search.component.scss'
})
export class MainSearchComponent {
  query: string = '';
  response: any;
  isLoading: boolean = false;

  constructor(private http: HttpClient) { }

  sendQuery() {
    if (!this.query.trim()) return;

    this.isLoading = true;
    this.response = null; // Clear previous response

    const payload = { query: this.query };
    this.http.post(`${environment.apiUrl}/query`, payload).subscribe({
      next: (res: any) => {
        this.response = res;
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Error fetching data', err);
        this.isLoading = false;
        // Optional: Handle error state in UI
        this.response = { Results: "⚠️ Error: Could not reach the intelligence engine. Please try again later." };
      }
    });
  }
}