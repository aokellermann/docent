declare module 'bun:test' {
  export const describe: (...args: any[]) => void;
  export const it: (...args: any[]) => void;
  export const test: (...args: any[]) => void;
  export const expect: any;
}
