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

  // DEV-only: preview the interactive ticket modal without a Python backend.
  // In DevTools console:
  //   __popCaptcha()            input captcha (chaoxing)
  //   __popCaptcha(3)           queue of 3 input captchas
  //   __popCaptcha('qrcode')    zhihuishu QR-login ticket (with countdown)
  //   __popCaptcha('hint')      zhihuishu slider ticket (text + link)
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
    // A fake QR-looking block so the modal's qrcode layout is previewable.
    const demoQrImage =
      'data:image/svg+xml;utf8,' +
      encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">' +
          '<rect width="240" height="240" fill="#fff"/>' +
          (() => {
            let cells = ''
            for (let y = 0; y < 12; y++) {
              for (let x = 0; x < 12; x++) {
                if ((x * 7 + y * 13 + ((x * y) % 5)) % 3 === 0) {
                  cells += `<rect x="${x * 20 + 4}" y="${y * 20 + 4}" width="14" height="14" fill="#111"/>`
                }
              }
            }
            return cells
          })() +
        '</svg>',
      )
    ;(window as any).__popCaptcha = (
      kindOrCount: 'captcha' | 'qrcode' | 'hint' | number = 'captcha',
      countArg = 1,
    ) => {
      const kind = typeof kindOrCount === 'number' ? 'captcha' : kindOrCount
      const count = typeof kindOrCount === 'number' ? kindOrCount : countArg
      const stamp = Math.floor(Date.now() / 1000)
      for (let i = 0; i < count; i++) {
        if (kind === 'qrcode') {
          store.ingest({
            id: `qr_${i}_${stamp}`,
            title: '智慧树扫码登录',
            message: `账号 ${i}：请使用智慧树 App 扫描二维码登录`,
            severity: 'critical',
            accountId: String(i),
            platform: 'zhihuishu',
            kind: 'qrcode',
            imageBase64: demoQrImage,
            timeoutSeconds: 180,
            resolved: false,
            createdAt: Date.now(),
          })
        } else if (kind === 'hint') {
          store.ingest({
            id: `hint_${i}_${stamp}`,
            title: '智慧树滑块验证',
            message: `账号 ${i}：请前往浏览器窗口手动完成滑块拖拽，完成后自动继续。如遇课程锁定可申诉：https://onlineweb.zhihuishu.com/appeal`,
            severity: 'critical',
            accountId: String(i),
            platform: 'zhihuishu',
            kind: 'hint',
            resolved: false,
            createdAt: Date.now(),
          })
        } else {
          store.ingest({
            id: `captcha_${i}_${stamp}`,
            title: '需要人工输入验证码',
            message: `账号 ${i} 在反爬验证码处受阻，AI 识别失败，请人工输入`,
            severity: 'critical',
            accountId: String(i),
            platform: 'chaoxing',
            kind: 'captcha',
            imageBase64: demoImage,
            options: ['输入验证码', '跳过此课程'],
            resolved: false,
            createdAt: Date.now(),
          })
        }
      }
      return `injected ${count} ${kind} ticket(s)`
    }
  }
}

bootstrap()
