import { createRouter, createWebHashHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/dashboard',
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
  },
  {
    path: '/course-atlas',
    name: 'course-atlas',
    component: () => import('@/views/CourseAtlasView.vue'),
  },
  {
    path: '/execution-studio',
    name: 'execution-studio',
    component: () => import('@/views/ExecutionStudioView.vue'),
  },
  {
    path: '/attention-queue',
    name: 'attention-queue',
    component: () => import('@/views/AttentionQueueView.vue'),
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
