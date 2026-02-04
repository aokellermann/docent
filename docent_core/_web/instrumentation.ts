import * as Sentry from '@sentry/nextjs';

export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./sentry.server.config');
  } else if (process.env.NEXT_RUNTIME === 'edge') {
    await import('./sentry.edge.config');
  }
}

export const onRequestError = (
  ...args: Parameters<typeof Sentry.captureRequestError>
) => {
  const [error, request, context] = args;
  const err = error instanceof Error ? error : new Error(String(error));
  // Log to stderr for AWS App Runner CloudWatch
  console.error(
    '[ServerError]',
    JSON.stringify({
      message: err.message,
      digest: 'digest' in err ? err.digest : undefined,
      path: request.path,
      method: request.method,
      routerKind: context.routerKind,
      routePath: context.routePath,
      routeType: context.routeType,
      stack: err.stack,
    })
  );
  Sentry.captureRequestError(error, request, context);
};
