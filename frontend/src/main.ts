import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from '@/router'
import App from '@/app/App.vue'

async function bootstrap() {
  const app = createApp(App)
  const pinia = createPinia()
  app.use(pinia)
  app.use(router)
  app.mount('#app')

  // DEV-only: preview the captcha modal without a Python backend.
  // In DevTools console:  __popCaptcha()   or   __popCaptcha(3)  for a queue.
  if (import.meta.env.DEV) {
    const { useCaptchaStore } = await import('@/app/stores/captcha.store')
    const store = useCaptchaStore(pinia)
    const demoImage =
      'data:image/svg+xml;utf8,' +
      encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="60">' +
          '<rect width="160" height="60" fill="#f0f0f0"/>' +
          '<text x="80" y="40" font-family="monospace" font-size="32" font-weight="bold"' +
          ' fill="#333" text-anchor="middle" letter-spacing="6" transform="rotate(-4 80 30)">A7K9</text>' +
          '<line x1="10" y1="20" x2="150" y2="45" stroke="#999" stroke-width="1"/>' +
        '</svg>',
      )
    ;(window as any).__popCaptcha = (count = 1) => {
      for (let i = 0; i < count; i++) {
        store.ingest({
          id: `captcha_${i}_${Math.floor(Date.now() / 1000) + i}`,
          title: '需要人工输入验证码',
          message: `账号 ${i} 在反爬验证码处受阻，AI 识别失败，请人工输入`,
          severity: 'critical',
          accountId: String(i),
          kind: 'captcha',
          imageBase64: demoImage,
          options: ['输入验证码', '跳过此课程'],
          resolved: false,
          createdAt: Date.now(),
        })
      }
      return `injected ${count} captcha ticket(s)`
    }
  }
}

bootstrap()
