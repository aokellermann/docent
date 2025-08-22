'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Plus, Trash2 } from 'lucide-react';
import { toast } from '@/hooks/use-toast';
import { apiRestClient } from '@/app/services/apiService';

interface ModelApiKey {
  id: string;
  provider: string;
  masked_api_key: string;
}

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'google', label: 'Google' },
] as const;

export default function ModelProvidersPage() {
  const [modelApiKeys, setModelApiKeys] = useState<ModelApiKey[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<string>('');
  const [apiKey, setApiKey] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const fetchModelApiKeys = async () => {
    try {
      const response = await apiRestClient.get('/model-api-keys');
      setModelApiKeys(response.data);
    } catch (error) {
      console.error('Failed to fetch model API keys:', error);
      toast({
        title: 'Error',
        description: 'Failed to load model API keys',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchModelApiKeys();
  }, []);

  const getAvailableProviders = () => {
    const usedProviders = new Set(modelApiKeys.map((key) => key.provider));
    return PROVIDERS.filter((provider) => !usedProviders.has(provider.value));
  };

  const handleSaveApiKey = async () => {
    if (!selectedProvider || !apiKey.trim()) return;

    setIsSaving(true);
    try {
      await apiRestClient.put('/model-api-keys', {
        provider: selectedProvider,
        api_key: apiKey.trim(),
      });

      setApiKey('');
      setSelectedProvider('');
      setIsDialogOpen(false);
      await fetchModelApiKeys();
    } catch (error) {
      console.error('Failed to save model API key:', error);
      toast({
        title: 'Error',
        description: 'Failed to save model API key',
        variant: 'destructive',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteApiKey = async (provider: string) => {
    try {
      await apiRestClient.delete(`/model-api-keys/${provider}`);
      await fetchModelApiKeys();
    } catch (error) {
      console.error('Failed to delete model API key:', error);
      toast({
        title: 'Error',
        description: 'Failed to delete model API key',
        variant: 'destructive',
      });
    }
  };

  const getProviderLabel = (provider: string) => {
    const providerConfig = PROVIDERS.find((p) => p.value === provider);
    return providerConfig?.label || provider;
  };

  const availableProviders = getAvailableProviders();

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Model Providers</h1>
          <p className="text-muted-foreground">
            You can use Docent with your own model API keys to access more
            models and higher rate limits.
          </p>
        </div>

        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogTrigger asChild>
            <Button disabled={availableProviders.length === 0}>
              <Plus className="mr-2 h-4 w-4" />
              Add Provider
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Model Provider</DialogTitle>
              <DialogDescription>
                Add an API key for a model provider. You can only have one key
                per provider.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label htmlFor="provider">Provider</Label>
                <Select
                  value={selectedProvider}
                  onValueChange={setSelectedProvider}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a provider" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableProviders.map((provider) => (
                      <SelectItem key={provider.value} value={provider.value}>
                        {provider.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="apiKey">API Key</Label>
                <Input
                  id="apiKey"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Enter your API key"
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setIsDialogOpen(false);
                  setSelectedProvider('');
                  setApiKey('');
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={handleSaveApiKey}
                disabled={isSaving || !selectedProvider || !apiKey.trim()}
              >
                {isSaving ? 'Saving...' : 'Save API Key'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {availableProviders.length === 0 && modelApiKeys.length > 0 && (
        <Card className="border-blue-200 bg-blue-50">
          <CardContent>
            <p className="text-sm text-blue-800">
              You have configured all available providers.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4">
        {isLoading ? (
          <Card>
            <CardContent className="pt-6">
              <div>Loading...</div>
            </CardContent>
          </Card>
        ) : modelApiKeys.length === 0 ? (
          <Card>
            <CardContent className="pt-6">
              <div className="text-center py-8 text-muted-foreground">
                No model providers configured. Add your first API key to get
                started.
              </div>
            </CardContent>
          </Card>
        ) : (
          modelApiKeys.map((key) => (
            <Card key={key.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <CardTitle className="text-lg">
                      {getProviderLabel(key.provider)}
                    </CardTitle>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDeleteApiKey(key.provider)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div>
                  <div className="font-mono text-sm bg-gray-50 p-2 rounded mt-1">
                    {key.masked_api_key}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
