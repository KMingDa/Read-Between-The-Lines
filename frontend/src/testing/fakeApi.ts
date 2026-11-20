// Test-only: an in-memory localStorage and a scripted fetch, for code that uses api/client.ts.
// Excluded from the app build (tsconfig.app.json); type-checked with the tests (tsconfig.test.json).

export type FetchCall = { url: string; init: RequestInit }

export const fakeApi = {
  calls: [] as FetchCall[],
  respond: (_call: FetchCall): Response | Promise<Response> => json(200, { ok: true }),
}

/** Fresh fakes for each test: empty storage, no recorded calls, every request answered 200 {ok: true}. */
export function resetFakeApi(): void {
  Object.defineProperty(globalThis, 'localStorage', { value: memoryStorage(), configurable: true })
  fakeApi.calls = []
  fakeApi.respond = () => json(200, { ok: true })
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    const call = { url: String(input), init: init ?? {} }
    fakeApi.calls.push(call)
    return fakeApi.respond(call)
  }) as typeof fetch
}

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

export function headersOf(call: FetchCall): Record<string, string> {
  return (call.init.headers ?? {}) as Record<string, string>
}

function memoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (key) => data.get(key) ?? null,
    key: (index) => [...data.keys()][index] ?? null,
    removeItem: (key) => {
      data.delete(key)
    },
    setItem: (key, value) => {
      data.set(key, String(value))
    },
  }
}
