import { Component } from '@angular/core';
import { MainSearchComponent } from "../../@shared/components/main-search/main-search.component";

@Component({
  selector: 'app-home',
  imports: [MainSearchComponent],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss'
})
export class HomeComponent {

}
