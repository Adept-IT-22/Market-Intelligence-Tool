import { Component } from '@angular/core';
import { MainSearchComponent } from "../../@shared/components/main-search/main-search.component";
import { BaseLayoutComponent } from '../../@shared/components/base-layout/base-layout.component';

@Component({
  selector: 'app-home',
  imports: [BaseLayoutComponent, MainSearchComponent],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss'
})
export class HomeComponent {

}
