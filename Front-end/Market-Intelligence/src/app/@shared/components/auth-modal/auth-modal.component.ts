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

    mode = signal<'login' | 'signup' | 'forgot' | 'change'>('login');
    isLoading = signal<boolean>(false);
    errorMessage = signal<string | null>(null);
    successMessage = signal<string | null>(null);

    authForm = this.fb.group({
        email: ['', [Validators.required, Validators.email]],
        password: ['', [Validators.required, Validators.minLength(6)]],
        displayName: [''],
        currentPassword: [''],
        newPassword: ['']
    });

    // Check if user is logged in (to show change password option)
    get isLoggedIn(): boolean {
        return this.auth.isAuthenticated();
    }

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

    showChangePassword() {
        this.mode.set('change');
        this.errorMessage.set(null);
        this.successMessage.set(null);
        this.authForm.patchValue({ currentPassword: '', newPassword: '' });
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

        if (this.mode() === 'change') {
            this.handleChangePassword();
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
        this.isLoading.set(true);
        this.errorMessage.set(null);

        this.auth.forgotPassword('').subscribe({
            next: (res) => {
                this.isLoading.set(false);
                this.successMessage.set(res.message + ' Contact: ' + res.contact);
            },
            error: (err) => {
                this.isLoading.set(false);
                this.errorMessage.set(err.error?.error || 'Failed to process request.');
            }
        });
    }

    private handleChangePassword() {
        const currentPassword = this.authForm.get('currentPassword')?.value;
        const newPassword = this.authForm.get('newPassword')?.value;

        if (!currentPassword || !newPassword) {
            this.errorMessage.set('Please enter both current and new password');
            return;
        }

        if (newPassword.length < 6) {
            this.errorMessage.set('New password must be at least 6 characters');
            return;
        }

        this.isLoading.set(true);
        this.errorMessage.set(null);

        this.auth.changePassword(currentPassword, newPassword).subscribe({
            next: (res) => {
                this.isLoading.set(false);
                this.successMessage.set(res.message);
            },
            error: (err) => {
                this.isLoading.set(false);
                this.errorMessage.set(err.error?.error || 'Failed to change password.');
            }
        });
    }

    close() {
        this.dialogRef.close();
    }
}
