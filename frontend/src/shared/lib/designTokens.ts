export const lightTokens: Record<string, string> = {
  '--bg': '#f4efe5',
  '--bg2': '#ede4d3',
  '--bg3': '#e8dcc8',
  '--panel': 'rgba(255, 251, 244, 0.84)',
  '--panel-strong': '#fff9f0',
  '--line': 'rgba(49, 61, 58, 0.14)',
  '--text': '#182321',
  '--muted': '#5b6b67',
  '--accent': '#0f766e',
  '--accent-soft': 'rgba(15, 118, 110, 0.12)',
  '--accent2': '#0d9488',
  '--warn': '#c05a2b',
  '--warn-soft': 'rgba(192, 90, 43, 0.12)',
  '--ok': '#28704c',
  '--ok-soft': 'rgba(40, 112, 76, 0.12)',
  '--gold': '#c39224',
  '--gold-soft': 'rgba(195, 146, 36, 0.12)',
  '--shadow': '0 18px 46px rgba(65, 49, 25, 0.12)',
  '--shadow-lg': '0 24px 60px rgba(42, 29, 14, 0.12)',
  '--radius-xl': '28px',
  '--radius-lg': '20px',
  '--radius-md': '14px',
  '--radius-sm': '10px',
  '--font-ui': '"Aptos", "Segoe UI Variable", "PingFang SC", "Microsoft YaHei UI", sans-serif',
  '--font-display': '"Bahnschrift", "Aptos Display", "Trebuchet MS", sans-serif',
  '--font-mono': '"Cascadia Code", "Fira Code", "Consolas", monospace',
}

export const darkTokens: Record<string, string> = {
  '--bg': '#0f1117',
  '--bg2': '#1a1d27',
  '--bg3': '#252836',
  '--panel': '#1a1d27',
  '--panel-strong': '#252836',
  '--line': '#2d3143',
  '--text': '#e1e4ed',
  '--muted': '#8b90a0',
  '--accent': '#6366f1',
  '--accent-soft': 'rgba(99, 102, 241, 0.12)',
  '--accent2': '#818cf8',
  '--warn': '#f97316',
  '--warn-soft': 'rgba(249, 115, 22, 0.12)',
  '--ok': '#22c55e',
  '--ok-soft': 'rgba(34, 197, 94, 0.12)',
  '--gold': '#eab308',
  '--gold-soft': 'rgba(234, 179, 8, 0.12)',
  '--shadow': '0 18px 46px rgba(0, 0, 0, 0.3)',
  '--shadow-lg': '0 24px 60px rgba(0, 0, 0, 0.4)',
  '--radius-xl': '28px',
  '--radius-lg': '20px',
  '--radius-md': '14px',
  '--radius-sm': '10px',
  '--font-ui': '"Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
  '--font-display': '"Bahnschrift", "Trebuchet MS", sans-serif',
  '--font-mono': '"Cascadia Code", "Fira Code", "Consolas", monospace',
}

export function applyTheme(theme: 'light' | 'dark'): void {
  const tokens = theme === 'light' ? lightTokens : darkTokens
  const root = document.documentElement
  for (const [key, value] of Object.entries(tokens)) {
    root.style.setProperty(key, value)
  }
  root.setAttribute('data-theme', theme)
}
