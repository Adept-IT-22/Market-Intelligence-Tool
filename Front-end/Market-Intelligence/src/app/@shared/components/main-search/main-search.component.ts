import { Component } from '@angular/core';

interface Message {
  text: string;
  sender: 'user' | 'bot';
}

@Component({
  selector: 'app-main-search',
  imports: [],
  templateUrl: './main-search.component.html',
  styleUrl: './main-search.component.scss'
})
export class MainSearchComponent {
}
