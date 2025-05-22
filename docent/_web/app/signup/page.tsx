'use client';

import { useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';

import { SignupForm } from '../components/auth/SignupForm';
import { UserResponse } from '../types/userTypes';

const SignupPage = () => {
  const router = useRouter();

  const handleSignupSuccess = (user: UserResponse) => {
    // Optional: redirect to dashboard or stay on page
    // router.push('/');
  };

  return (
    <ScrollArea className="h-screen">
      <div className="container mx-auto py-8 px-4 max-w-md">
        <div className="space-y-6">
          {/* Header */}
          <div className="text-center space-y-2">
            <h1 className="text-2xl font-bold tracking-tight">
              Sign up for Docent
            </h1>
            <p className="text-sm text-gray-600">
              Enter your email address to get started
            </p>
          </div>

          {/* Signup Form */}
          <SignupForm onSuccess={handleSignupSuccess} />

          {/* Back to Dashboard */}
          <div className="text-center">
            <Button
              variant="ghost"
              onClick={() => router.push('/')}
              className="text-sm"
            >
              Back to Dashboard
            </Button>
          </div>
        </div>
      </div>
    </ScrollArea>
  );
};

export default SignupPage;
