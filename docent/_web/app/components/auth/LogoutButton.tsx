'use client';

import { Button } from '@/components/ui/button';
import { toast } from '@/hooks/use-toast';

import { useUser } from '../../contexts/UserContext';

interface LogoutButtonProps {
  variant?:
    | 'default'
    | 'destructive'
    | 'outline'
    | 'secondary'
    | 'ghost'
    | 'link';
  size?: 'default' | 'sm' | 'lg' | 'icon';
  className?: string;
}

export const LogoutButton = ({
  variant = 'outline',
  size = 'default',
  className,
}: LogoutButtonProps) => {
  const { logout } = useUser();

  const handleLogout = async () => {
    try {
      await logout();
      toast({
        title: 'Success',
        description: 'You have been logged out successfully.',
      });
    } catch (error) {
      toast({
        title: 'Error',
        description: 'There was an error logging out. Please try again.',
        variant: 'destructive',
      });
    }
  };

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleLogout}
      className={className}
    >
      Log Out
    </Button>
  );
};
