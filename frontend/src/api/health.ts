export async function checkHealth(signal: AbortSignal): Promise<boolean> {
  const response = await fetch('/api/health', { signal })
  return response.ok
}
