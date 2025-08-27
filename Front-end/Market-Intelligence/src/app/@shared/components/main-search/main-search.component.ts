import { HttpClient } from '@angular/common/http';
import { Component, Injectable } from '@angular/core';
import { environment } from '../../../../environments/environment';
import { FormsModule } from '@angular/forms'
import { CommonModule } from '@angular/common';
import { MarkdownModule } from 'ngx-markdown';

@Component({
  selector: 'app-main-search',
  standalone: true,
  imports: [FormsModule, CommonModule, MarkdownModule],
  templateUrl: './main-search.component.html',
  styleUrl: './main-search.component.scss'
})

export class MainSearchComponent {
  query: string = ""
  response: any;

  constructor(private http: HttpClient){}

  sendQuery(){
    //If there's no query exit
    if (!this.query.trim()) return;

    console.log(this.query)

    this.http.get(
      `${environment.apiUrl}/query`, 
      {params: {q: this.query}}
    ).
      subscribe({
        next: (response) => {
          console.log('Response:', response);
          this.response = response;
        },
        error: (err) => {
          console.error('Error:', err);
        }
      })
  }
}