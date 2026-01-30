import { Component, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../services/auth.service';

@Component({
    selector: 'app-auth-modal',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        ReactiveFormsModule,
        MatDialogModule,
        MatFormFieldModule,
        MatInputModule,
        MatButtonModule,
        MatIconModule
    ],
    templateUrl: './auth-modal.component.html',
    styleUrl: './auth-modal.component.scss'
})
export class AuthModalComponent {
    private fb = inject(FormBuilder);
    private auth = inject(AuthService);
    private dialogRef = inject(MatDialogRef<AuthModalComponent>);

    mode = signal<'login' | 'signup' | 'forgot'>('login');
    isLoading = signal<boolean>(false);
    errorMessage = signal<string | null>(null);
    successMessage = signal<string | null>(null);

    authForm = this.fb.group({
        email: ['', [Validators.required, Validators.email]],
        password: ['', [Validators.required, Validators.minLength(6)]],
        displayName: ['']
    });

    switchMode() {
        this.mode.set(this.mode() === 'login' ? 'signup' : 'login');
        this.errorMessage.set(null);
        this.successMessage.set(null);
    }

    showForgotPassword() {
        this.mode.set('forgot');
        this.errorMessage.set(null);
        this.successMessage.set(null);
    }

    backToLogin() {
        this.mode.set('login');
        this.errorMessage.set(null);
        this.successMessage.set(null);
    }

    onSubmit() {
        if (this.mode() === 'forgot') {
            this.handleForgotPassword();
            return;
        }

        if (this.authForm.invalid) return;

        this.isLoading.set(true);
        this.errorMessage.set(null);

        const { email, password, displayName } = this.authForm.value;

        const authObs = this.mode() === 'login'
            ? this.auth.login(email!, password!)
            : this.auth.signup(email!, password!, displayName || undefined);

        authObs.subscribe({
            next: () => {
                this.isLoading.set(false);
                this.dialogRef.close(true);
            },
            error: (err) => {
                this.isLoading.set(false);
                this.errorMessage.set(err.error?.error || 'Authentication failed. Please try again.');
            }
        });
    }

    private handleForgotPassword() {
        const email = this.authForm.get('email')?.value;
        if (!email) {
            this.errorMessage.set('Please enter your email address');
            return;
        }

        this.isLoading.set(true);
        this.errorMessage.set(null);

        this.auth.forgotPassword(email).subscribe({
            next: (res) => {
                this.isLoading.set(false);
                this.successMessage.set(res.message + ' ' + res.contact);
            },
            error: (err) => {
                this.isLoading.set(false);
                this.errorMessage.set(err.error?.error || 'Failed to process request. Please try again.');
            }
        });
    }

    close() {
        this.dialogRef.close();
    }
}
