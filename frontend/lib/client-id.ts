export function createClientId() {
  const cryptoApi = globalThis.crypto;

  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }

  const randomPart = Math.random().toString(36).slice(2, 10);
  return `client-${Date.now().toString(36)}-${randomPart}`;
}
