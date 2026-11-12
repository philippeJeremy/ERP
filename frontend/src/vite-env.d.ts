/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Version injectée au build par le workflow de release (tag Git). */
  readonly VITE_APP_VERSION?: string
}
