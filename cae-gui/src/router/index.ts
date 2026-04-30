import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/diagnose',
    },
    {
      path: '/project',
      name: 'project',
      component: () => import('@/views/ProjectView.vue'),
    },
    {
      path: '/solve',
      name: 'solve',
      component: () => import('@/views/SolveView.vue'),
    },
    {
      path: '/viewer',
      name: 'viewer',
      component: () => import('@/views/ViewerView.vue'),
    },
    {
      path: '/diagnose',
      name: 'diagnose',
      component: () => import('@/views/DiagnoseView.vue'),
    },
    {
      path: '/docker',
      name: 'docker',
      component: () => import('@/views/DockerView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
    },
  ],
})

export default router
