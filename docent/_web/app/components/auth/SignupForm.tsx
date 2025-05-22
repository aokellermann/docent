'use client';

import { Loader2 } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from '@/hooks/use-toast';

import { apiRestClient } from '../../services/apiService';
import { UserCreateRequest, UserResponse } from '../../types/userTypes';

interface SignupFormProps {
  onSuccess?: (user: UserResponse) => void;
}

export const SignupForm = ({ onSuccess }: SignupFormProps) => {
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a valid email address',
        variant: 'destructive',
      });
      return;
    }

    setIsSubmitting(true);
    try {
      const request: UserCreateRequest = { email: email.trim() };
      const response = await apiRestClient.post<UserResponse>(
        '/signup',
        request
      );

      // Store user data locally (in-memory for now)
      localStorage.setItem('docent_user', JSON.stringify(response.data));

      toast({
        title: 'Success',
        description: `Welcome! User created with ID: ${response.data.user_id}`,
      });

      // Display the result
      console.log('User signup result:', response.data);

      // Call success callback if provided
      onSuccess?.(response.data);
    } catch (error) {
      console.error('Failed to sign up:', error);
      toast({
        title: 'Error',
        description: 'Failed to sign up. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="email">Email Address</Label>
        <Input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Enter your email address"
          disabled={isSubmitting}
          required
        />
      </div>

      <Button
        type="submit"
        className="w-full"
        disabled={isSubmitting || !email.trim()}
      >
        {isSubmitting ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Signing up...
          </>
        ) : (
          'Sign Up'
        )}
      </Button>
    </form>
  );
};
