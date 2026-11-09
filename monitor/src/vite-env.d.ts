/// <reference types="vite/client" />

declare module "*.json" {
  const value: { items: { id: string; label: string; done: boolean; evidence: string }[] };
  export default value;
}

interface ImportMetaEnv {
  readonly VITE_BACKEND_URL?: string;
  readonly VITE_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
